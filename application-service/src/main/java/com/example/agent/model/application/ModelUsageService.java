package com.example.agent.model.application;

import com.example.agent.model.domain.ModelPricingVersion;
import com.example.agent.model.domain.ModelReference;
import com.example.agent.model.domain.RuntimeTaskSnapshot;
import com.example.agent.model.domain.UsageRecordDraft;
import com.example.agent.model.domain.UsageRecordInput;
import com.example.agent.model.domain.UsageReportResult;
import com.example.agent.model.infrastructure.PricingStore;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.model.infrastructure.UsageStore;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 使用明细入库与成本估算。
 *
 * <p>用户归属、模型一致性与成本口径都由服务端从任务行和定价表推导，不信任上报方字段；
 * 不通过的记录计入 {@code rejected} 并跳过，不返回 4xx 中断整批——批量上报是尽力而为的
 * 计量链路，单条脏数据不应让整批丢失。</p>
 *
 * <p>成本在入库时按「调用发生时刻」定格的定价版本计算，后续调价不会改写历史记录；
 * 拿不到定价或 token 用量时标记为 {@code UNKNOWN}，绝不写 0 或猜测金额。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ModelUsageService {

    static final String CREDENTIAL_SOURCE_BYOK = "BYOK";

    static final String COST_STATUS_ESTIMATED = "ESTIMATED";

    static final String COST_STATUS_UNKNOWN = "UNKNOWN";

    static final String COST_STATUS_BYOK_NOT_BILLED = "BYOK_NOT_BILLED";

    static final String COST_BEARER_PLATFORM = "PLATFORM";

    static final String COST_BEARER_USER = "USER";

    private static final BigDecimal TOKENS_PER_MILLION = new BigDecimal("1000000");

    private static final int COST_SCALE = 6;

    private final RuntimeTaskStore runtimeTaskStore;

    private final UsageStore usageStore;

    private final PricingStore pricingStore;

    private final ModelRuntimeGuard runtimeGuard;

    /**
     * 批量写入使用明细，按 {@code invocation_id} 幂等。
     *
     * @param records 上报记录
     * @return 实际入库、幂等命中与被拒绝的条数
     */
    @Transactional
    public UsageReportResult report(List<UsageRecordInput> records) {
        runtimeGuard.requireEnabled();
        Map<UUID, RuntimeTaskSnapshot> tasks = loadTasks(records);
        List<PendingUsage> pending = new ArrayList<>(records.size());
        int rejected = 0;
        for (UsageRecordInput record : records) {
            Optional<PendingUsage> accepted = accept(record, tasks.get(record.taskId()));
            if (accepted.isPresent()) {
                pending.add(accepted.get());
            } else {
                rejected++;
            }
        }
        if (pending.isEmpty()) {
            if (rejected > 0) {
                log.warn("使用明细全部被拒绝 count={}", rejected);
            }
            return new UsageReportResult(0, 0, rejected);
        }
        Map<String, List<ModelPricingVersion>> pricing = loadPricing(pending);
        List<UsageRecordDraft> rows = pending.stream()
                .map(item -> toDraft(item, pricing))
                .toList();
        int accepted = usageStore.insertIgnoreDuplicates(rows);
        int duplicated = rows.size() - accepted;
        if (rejected > 0) {
            log.warn("使用明细部分被拒绝 rejected={} accepted={} duplicated={}", rejected, accepted, duplicated);
        }
        return new UsageReportResult(accepted, duplicated, rejected);
    }

    private Map<UUID, RuntimeTaskSnapshot> loadTasks(List<UsageRecordInput> records) {
        Set<UUID> taskIds = records.stream()
                .map(UsageRecordInput::taskId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
        if (taskIds.isEmpty()) {
            return Map.of();
        }
        return runtimeTaskStore.findByIds(taskIds).stream()
                .collect(Collectors.toMap(RuntimeTaskSnapshot::id, Function.identity()));
    }

    /**
     * 记录与任务不一致时返回空：任务不存在、模型引用与任务解析结果不符、凭证来源不符。
     * 用户 ID、线程 ID 与凭证来源一律取自任务行，上报方无法伪造归属。
     */
    private Optional<PendingUsage> accept(UsageRecordInput record, RuntimeTaskSnapshot task) {
        if (task == null
                || record.invocationId() == null
                || !Objects.equals(task.credentialSource(), record.credentialSource())) {
            return Optional.empty();
        }
        Optional<ModelReference> reference = ModelReference.tryParse(record.modelKey());
        if (reference.isEmpty()
                || !Objects.equals(reference.get().provider(), record.provider())
                || !Objects.equals(reference.get().reference(), task.resolvedModel())) {
            return Optional.empty();
        }
        return Optional.of(new PendingUsage(
                record.invocationId(),
                task,
                record.modelRole(),
                reference.get().provider(),
                reference.get().modelKey(),
                record.promptTokens(),
                record.completionTokens(),
                record.latencyMs(),
                record.status(),
                record.errorType(),
                record.occurredAt()));
    }

    /**
     * 一次装载本批次涉及的全部定价版本，避免逐条查询。
     *
     * <p>查询按 Provider 与模型键分别过滤，可能多取到不属于同一组合的行；
     * 后续按 {@code provider:modelKey} 精确分组，不会误用其他组合的价格。</p>
     */
    private Map<String, List<ModelPricingVersion>> loadPricing(List<PendingUsage> pending) {
        Set<String> providers = new HashSet<>();
        Set<String> modelKeys = new HashSet<>();
        for (PendingUsage item : pending) {
            providers.add(item.provider());
            modelKeys.add(item.modelKey());
        }
        return pricingStore.findByModels(providers, modelKeys).stream()
                .collect(Collectors.groupingBy(price -> pricingKey(price.provider(), price.modelKey())));
    }

    private UsageRecordDraft toDraft(PendingUsage item, Map<String, List<ModelPricingVersion>> pricing) {
        List<ModelPricingVersion> versions =
                pricing.getOrDefault(pricingKey(item.provider(), item.modelKey()), List.of());
        Cost cost = estimateCost(item, versions);
        return new UsageRecordDraft(
                item.invocationId(),
                item.task().id(),
                item.task().userPublicId(),
                item.task().threadId(),
                item.modelRole(),
                item.provider(),
                item.modelKey(),
                item.task().credentialSource(),
                item.promptTokens(),
                item.completionTokens(),
                item.latencyMs(),
                item.status(),
                item.errorType(),
                cost.amount(),
                cost.status(),
                cost.bearer(),
                cost.currency(),
                item.occurredAt());
    }

    /**
     * 成本估算规则：
     * <ol>
     *   <li>BYOK：用户自带凭证，平台不承担费用，也不估算金额；</li>
     *   <li>托管模型：缺少定价或缺任一 token 用量 → {@code UNKNOWN}，金额留空；</li>
     *   <li>其余：按生效版本价格计算，状态 {@code ESTIMATED}。</li>
     * </ol>
     */
    private static Cost estimateCost(PendingUsage item, List<ModelPricingVersion> versions) {
        if (CREDENTIAL_SOURCE_BYOK.equals(item.task().credentialSource())) {
            return new Cost(null, COST_STATUS_BYOK_NOT_BILLED, COST_BEARER_USER, null);
        }
        ModelPricingVersion price = resolvePrice(versions, item.occurredAt());
        if (price == null || item.promptTokens() == null || item.completionTokens() == null) {
            return new Cost(null, COST_STATUS_UNKNOWN, COST_BEARER_PLATFORM, null);
        }
        BigDecimal amount = lineCost(price.inputPricePerMillion(), item.promptTokens())
                .add(lineCost(price.outputPricePerMillion(), item.completionTokens()));
        return new Cost(amount, COST_STATUS_ESTIMATED, COST_BEARER_PLATFORM, price.currency());
    }

    /**
     * 选择调用发生时刻的生效版本。
     *
     * <p>Mapper 已按 {@code effectiveFrom} 倒序返回，首个不晚于调用时间的记录即生效版本；
     * 全部晚于调用时间说明当时尚无定价，返回 {@code null}。</p>
     */
    private static ModelPricingVersion resolvePrice(
            List<ModelPricingVersion> versions, OffsetDateTime occurredAt) {
        for (ModelPricingVersion version : versions) {
            if (!version.effectiveFrom().isAfter(occurredAt)) {
                return version;
            }
        }
        return null;
    }

    private static BigDecimal lineCost(BigDecimal pricePerMillion, int tokens) {
        return pricePerMillion.multiply(BigDecimal.valueOf(tokens))
                .divide(TOKENS_PER_MILLION, COST_SCALE, RoundingMode.HALF_UP);
    }

    private static String pricingKey(String provider, String modelKey) {
        return provider + ":" + modelKey;
    }

    /** 通过校验、等待写入的计量记录；凭证来源来自任务行，是成本归属的权威依据。 */
    private record PendingUsage(
            UUID invocationId,
            RuntimeTaskSnapshot task,
            String modelRole,
            String provider,
            String modelKey,
            Integer promptTokens,
            Integer completionTokens,
            Integer latencyMs,
            String status,
            String errorType,
            OffsetDateTime occurredAt) {
    }

    /** 成本估算结果；{@code amount} 为空表示不估算，绝不写 0 冒充已知成本。 */
    private record Cost(BigDecimal amount, String status, String bearer, String currency) {
    }
}
