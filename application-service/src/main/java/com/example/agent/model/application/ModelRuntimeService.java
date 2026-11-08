package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ModelReference;
import com.example.agent.model.domain.ModelTaskView;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.domain.QuotaExceededDetail;
import com.example.agent.model.domain.QuotaSnapshot;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.domain.RuntimeTaskSnapshot;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.QuotaStore;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 运行时任务服务：模型解析 + 额度扣减 + 任务签发的唯一入口。
 *
 * <p>额度在任务创建成功时计数（含之后调用失败的情况），因为额度衡量的是「进入执行阶段
 * 的请求数」，不是「成功的模型调用数」。扣减与任务写入在同一事务内：任务插入失败会
 * 一并回滚额度，不会出现「扣了额度却没拿到任务」。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ModelRuntimeService {

    static final String CREDENTIAL_SOURCE_MANAGED = "MANAGED";

    static final String CREDENTIAL_SOURCE_BYOK = "BYOK";

    private static final String TASK_STATUS_ACTIVE = "ACTIVE";

    private static final String QUOTA_TYPE_DAILY_REQUESTS = "daily_requests";

    private final ModelCatalogService modelCatalogService;
    private final ModelRuntimeGuard runtimeGuard;
    private final QuotaStore quotaStore;
    private final RuntimeTaskStore runtimeTaskStore;
    private final ProviderConnectionStore connectionStore;
    private final ModelRuntimeProperties properties;
    private final Clock modelRuntimeUtcClock;

    /**
     * 创建运行时任务并占用一次额度。
     *
     * <p>带幂等键时，同键重放直接返回既有任务且不再扣额度；并发重放由唯一索引兜底，
     * 插入返回 0 后回读对方已提交的任务。幂等窗口以任务 TTL 为准，超窗重放返回 409。</p>
     *
     * @param userPublicId   用户公开 ID（来自用户令牌 {@code sub}）
     * @param threadId       会话线程标识
     * @param requestedModel 请求指定模型，为空表示 Auto
     * @param idempotencyKey 调用方幂等键，为空表示不启用幂等
     * @return 不含凭证的任务视图
     * @throws BusinessException 模型不可用 403、额度超限 429、运行时未启用 404、幂等冲突 409
     */
    @Transactional
    public ModelTaskView createTask(
            UUID userPublicId, String threadId, String requestedModel, String idempotencyKey) {
        runtimeGuard.requireEnabled();
        if (idempotencyKey != null) {
            RuntimeTaskSnapshot replay = runtimeTaskStore.findByUserAndKey(userPublicId, idempotencyKey);
            if (replay != null) {
                return replayTask(replay, threadId, requestedModel);
            }
        }
        ResolvedModel resolvedModel = requestedModel == null || requestedModel.isBlank()
                ? modelCatalogService.resolveAuto()
                : modelCatalogService.requireAvailable(requestedModel, userPublicId);
        // 凭证来源在扣额度前确定：凭证已撤销时直接失败，避免白扣一次额度
        ByokTarget byok = resolveByok(userPublicId, resolvedModel.provider());
        OffsetDateTime expiresAt = OffsetDateTime.now(modelRuntimeUtcClock).plus(properties.getTaskTtl());
        RuntimeTaskSnapshot task = new RuntimeTaskSnapshot(
                UUID.randomUUID(),
                userPublicId,
                threadId,
                requestedModel,
                resolvedModel.reference(),
                byok == null ? CREDENTIAL_SOURCE_MANAGED : CREDENTIAL_SOURCE_BYOK,
                byok == null ? null : byok.credentialId(),
                byok == null ? null : byok.baseUrl(),
                TASK_STATUS_ACTIVE,
                expiresAt,
                null,
                idempotencyKey);
        int inserted = runtimeTaskStore.insert(task);
        // 只有带键时 SQL 才有 ON CONFLICT 子句，返回 0 才代表幂等冲突
        if (idempotencyKey != null && inserted == 0) {
            // 并发重放撞唯一索引：对方事务已提交，本事务不扣额度，直接复用其任务
            RuntimeTaskSnapshot existing = runtimeTaskStore.findByUserAndKey(userPublicId, idempotencyKey);
            if (existing == null) {
                log.warn("幂等冲突但未读到既有任务 userId={} threadId={}", userPublicId, threadId);
                throw new BusinessException(ModelErrorCode.IDEMPOTENCY_CONFLICT);
            }
            log.info("幂等重放复用既有任务 taskId={} userId={}", existing.id(), userPublicId);
            return replayTask(existing, threadId, requestedModel);
        }
        // 先插入任务再扣额度：额度失败时整个事务回滚，任务与额度的原子性不变
        consumeDailyQuota(userPublicId);
        log.info("运行时任务已创建 taskId={} userId={} model={} source={} idempotent={}",
                task.id(), userPublicId, resolvedModel.reference(), task.credentialSource(),
                idempotencyKey != null);
        return viewOf(task, resolvedModel.capabilities());
    }

    /**
     * 把已到期且仍为 ACTIVE 的任务标记为 EXPIRED。
     *
     * <p>只改状态不删行：使用明细通过 {@code task_id} 外键引用任务，删除会破坏历史台账。</p>
     *
     * @return 本次标记的行数
     */
    @Transactional
    public int expireStaleTasks() {
        runtimeGuard.requireEnabled();
        int expired = runtimeTaskStore.markExpiredBefore(OffsetDateTime.now(modelRuntimeUtcClock));
        if (expired > 0) {
            log.info("运行时任务过期标记完成 expired={}", expired);
        }
        return expired;
    }

    /**
     * 校验同键任务能否作为本次请求的重放结果。
     *
     * <p>同键但线程、模型不同说明该键被复用到了另一请求；任务已过期或非 ACTIVE
     * 说明幂等窗口已关闭。两种情况都必须拒绝，不能把失效任务交给调用方继续兑换。</p>
     */
    private ModelTaskView replayTask(RuntimeTaskSnapshot existing, String threadId, String requestedModel) {
        boolean isSameRequest = Objects.equals(existing.threadId(), threadId)
                && Objects.equals(existing.requestedModel(), requestedModel);
        boolean isValid = TASK_STATUS_ACTIVE.equals(existing.status())
                && !existing.expiresAt().isBefore(OffsetDateTime.now(modelRuntimeUtcClock));
        if (!isSameRequest || !isValid) {
            log.warn("幂等键冲突 taskId={} threadId={} status={}", existing.id(), existing.threadId(),
                    existing.status());
            throw new BusinessException(ModelErrorCode.IDEMPOTENCY_CONFLICT);
        }
        return viewOf(existing, modelCatalogService.findCapabilities(existing.resolvedModel()));
    }

    /**
     * 读取本用户的运行时任务，供 Agent 在 TTL 内复用解析结果。
     *
     * @param userPublicId 用户公开 ID
     * @param taskId       任务标识
     * @return 任务视图
     * @throws BusinessException 任务不存在、已过期或不属于该用户时统一 404，避免泄露存在性
     */
    @Transactional(readOnly = true)
    public ModelTaskView readTask(UUID userPublicId, UUID taskId) {
        runtimeGuard.requireEnabled();
        RuntimeTaskSnapshot task = findOwnedTask(userPublicId, taskId);
        if (task.expiresAt().isBefore(OffsetDateTime.now(modelRuntimeUtcClock))) {
            throw new BusinessException(ModelErrorCode.TASK_NOT_FOUND);
        }
        return viewOf(task, modelCatalogService.findCapabilities(task.resolvedModel()));
    }

    /**
     * 组装任务视图。
     *
     * <p>能力位由调用方给出：创建路径直接复用刚解析的模型快照，幂等重放与任务读取
     * 路径按引用回查目录，避免为同一份能力位多打一次查询。</p>
     */
    private ModelTaskView viewOf(RuntimeTaskSnapshot task, List<String> capabilities) {
        ModelReference reference = ModelReference.parse(task.resolvedModel());
        return new ModelTaskView(
                task.id(), reference.provider(), task.resolvedModel(), task.credentialSource(),
                task.credentialId(), task.baseUrl(), task.expiresAt(), capabilities);
    }

    /**
     * 判定本次任务是否使用用户自带凭证。
     *
     * <p>规则：BYOK 开启且该用户对 Provider 存在 ACTIVE 连接时使用自带凭证；
     * 连接存在但凭证已撤销属于不一致状态，按「凭证不可用」直接失败，禁止静默回落到平台密钥。</p>
     */
    private ByokTarget resolveByok(UUID userPublicId, String providerCode) {
        if (!properties.isByokEnabled()) {
            return null;
        }
        ProviderConnectionView connection = connectionStore.findActiveViewByProvider(userPublicId, providerCode);
        if (connection == null) {
            return null;
        }
        if (connection.credential() == null) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REVOKED);
        }
        return new ByokTarget(connection.credential().id(), connection.baseUrl());
    }

    private record ByokTarget(UUID credentialId, String baseUrl) {
    }

    private RuntimeTaskSnapshot findOwnedTask(UUID userPublicId, UUID taskId) {
        List<RuntimeTaskSnapshot> tasks = runtimeTaskStore.findByIds(List.of(taskId));
        if (tasks.isEmpty() || !Objects.equals(tasks.get(0).userPublicId(), userPublicId)) {
            throw new BusinessException(ModelErrorCode.TASK_NOT_FOUND);
        }
        return tasks.get(0);
    }

    /**
     * 单语句原子扣减；返回空表示当日额度已满。
     *
     * <p>超限后再读一次额度行只用于组装错误详情，不参与扣减判断。</p>
     */
    private void consumeDailyQuota(UUID userPublicId) {
        LocalDate quotaDate = LocalDate.now(modelRuntimeUtcClock);
        int dailyLimit = properties.getQuota().getDailyRequests();
        QuotaSnapshot consumed = quotaStore.tryConsume(userPublicId, quotaDate, dailyLimit);
        if (consumed != null) {
            return;
        }
        QuotaSnapshot current = quotaStore.find(userPublicId, quotaDate);
        int used = current == null ? 0 : current.usedCount();
        int limit = current == null ? dailyLimit : current.limitCount();
        log.warn("每日请求额度已用尽 userId={} quotaDate={} used={} limit={}",
                userPublicId, quotaDate, used, limit);
        throw new BusinessException(
                ModelErrorCode.QUOTA_EXCEEDED,
                ModelErrorCode.QUOTA_EXCEEDED.message(),
                new QuotaExceededDetail(QUOTA_TYPE_DAILY_REQUESTS, limit, used, resetAt(quotaDate)));
    }

    private OffsetDateTime resetAt(LocalDate quotaDate) {
        return quotaDate.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }
}
