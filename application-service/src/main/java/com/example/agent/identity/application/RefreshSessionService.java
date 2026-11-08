package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.IdentityErrorCode;
import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshSessionFamily;
import com.example.agent.identity.domain.RefreshTokens;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.web.dto.SessionResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.AppSecurityProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 刷新会话服务：签发、轮换、撤销与清理。
 *
 * <p>安全模型：Refresh Token 是不透明随机串，服务端只存摘要；每次刷新都轮换，
 * 旧令牌立即作废。旧令牌再次出现意味着它已脱离合法客户端，因此按令牌族整体撤销。
 * 唯一的例外是并发刷新：宽限期内的重复出示按冲突处理（见 {@code rotationGrace}）。</p>
 */
@Service
@RequiredArgsConstructor
public class RefreshSessionService {

    private static final String REASON_LOGOUT = "logout";
    private static final String REASON_EXPIRED = "expired";
    private static final String REASON_REPLAY = "replay";
    private static final String REASON_USER_DISABLED = "user_disabled";
    private static final String REASON_PASSWORD_CHANGE = "password_change";

    /** 过期未清理的会话再多保留一段时间，便于排查「为什么被强制重登」。 */
    private static final Duration PURGE_RETENTION = Duration.ofDays(7);

    private final RefreshSessionStore refreshSessionStore;
    private final UserDirectory userDirectory;
    private final AppSecurityProperties properties;
    private final AuthAuditRecorder authAuditRecorder;

    /**
     * 登录成功后开启一个令牌族。
     *
     * @param userId 用户内部主键
     * @return 明文令牌、所属令牌族与绝对过期时间（Cookie 的 Max-Age 用后者）
     */
    @Transactional
    public IssuedRefreshToken start(Long userId) {
        Instant now = Instant.now();
        AppSecurityProperties.Refresh refresh = properties.getRefresh();
        Instant absoluteExpiresAt = now.plus(refresh.getAbsoluteTtl());
        Instant idleExpiresAt = now.plus(refresh.getIdleTtl());
        return issue(userId, UUID.randomUUID(), absoluteExpiresAt, idleExpiresAt);
    }

    /**
     * 撤销指定用户除当前令牌族之外的全部会话。
     *
     * <p>用于改密：其他设备下次刷新即失效，当前设备继续可用。撤销原因是
     * {@code password_change}，便于排查「为什么被强制重新登录」。</p>
     *
     * @param userId          用户内部主键
     * @param currentFamilyId 需要保留的令牌族，即当前设备所在族
     * @return 实际撤销的会话行数
     */
    @Transactional
    public int revokeAllExceptFamily(Long userId, UUID currentFamilyId) {
        return refreshSessionStore.revokeAllExceptFamily(
                userId, currentFamilyId, REASON_PASSWORD_CHANGE, Instant.now());
    }

    /**
     * 分页查询当前用户的登录设备。
     *
     * <p>{@code current} 只用于展示：它来自访问令牌的 {@code sid} claim，不参与任何鉴权判断。
     * 存量令牌没有 {@code sid} 时全部返回 {@code false}，不报错，避免旧令牌让整页不可用。</p>
     *
     * @param publicId        令牌 {@code sub}
     * @param currentFamilyId 令牌 {@code sid}，可为 {@code null}
     * @param query           分页参数
     * @return 设备列表与总数
     * @throws BusinessException 用户已不存在时抛 {@code UNAUTHORIZED}
     */
    @Transactional(readOnly = true)
    public PageResult<SessionResponse> listFamilies(String publicId, String currentFamilyId, PageQuery query) {
        Long userId = requireUserId(publicId);
        long total = refreshSessionStore.countFamilies(userId);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<RefreshSessionFamily> families =
                refreshSessionStore.listFamilies(userId, query.offset(), query.getSize());
        List<SessionResponse> sessions = families.stream()
                .map(family -> toSessionResponse(family, currentFamilyId))
                .toList();
        return PageResult.of(sessions, total, query);
    }

    /**
     * 撤销指定设备（令牌族）的登录会话。
     *
     * <p>当前设备不允许在这里撤销：它需要同步清除浏览器 Cookie，应走 {@code /auth/logout}。
     * 归属校验下推到 SQL 的 {@code user_id} 条件，因此「他人的族」与「不存在」返回同一错误，
     * 不泄露其他账号是否存在该族。</p>
     *
     * @param publicId        令牌 {@code sub}
     * @param familyId        目标令牌族标识（UUID 文本）
     * @param currentFamilyId 令牌 {@code sid}，用于拦截「撤销自己」
     * @throws BusinessException 标识格式非法（{@code PARAM_INVALID}）、目标是当前设备
     *                           （{@code 30002}）、目标不存在或不属于当前用户（{@code 40105}）
     */
    @Transactional
    public void revokeFamily(String publicId, String familyId, String currentFamilyId) {
        Long userId = requireUserId(publicId);
        UUID targetFamilyId = parseFamilyId(familyId);
        if (currentFamilyId != null && currentFamilyId.equalsIgnoreCase(targetFamilyId.toString())) {
            throw new BusinessException(CommonErrorCode.RESOURCE_CONFLICT, "不能删除当前正在使用的会话，请使用退出登录");
        }
        int revoked = refreshSessionStore.revokeFamilyForUser(userId, targetFamilyId, REASON_LOGOUT, Instant.now());
        if (revoked == 0) {
            throw new BusinessException(IdentityErrorCode.SESSION_NOT_FOUND);
        }
    }

    /**
     * 撤销当前用户的全部登录会话（退出所有设备）。
     *
     * @param publicId 令牌 {@code sub}
     * @return 撤销的会话行数；Cookie 已失效时也不报错，符合「撤销是幂等的」
     */
    @Transactional
    public int logoutAll(String publicId) {
        return refreshSessionStore.revokeAllForUser(requireUserId(publicId), REASON_LOGOUT, Instant.now());
    }

    /**
     * 管理端禁用账号后撤销其全部刷新会话。
     *
     * <p>已签发的 Access Token 无法召回，仍会在最长剩余有效期内可用；
     * 下一次刷新即被拒绝。撤销原因是 {@code user_disabled}，便于排查。</p>
     *
     * @param userId 用户内部主键
     * @return 实际撤销的会话行数
     */
    @Transactional
    public int revokeAllForDisabledUser(Long userId) {
        return refreshSessionStore.revokeAllForUser(userId, REASON_USER_DISABLED, Instant.now());
    }

    /**
     * 用旧令牌换新令牌，并作废旧令牌。
     *
     * @param rawToken 客户端出示的令牌明文
     * @return 令牌归属用户与新令牌
     * @throws BusinessException 令牌不存在、已撤销、已过期或用户不可用时抛出 401
     */
    @Transactional
    public RefreshedSession rotate(String rawToken) {
        Instant now = Instant.now();
        RefreshSession session = lockSession(rawToken);
        rejectIfRevoked(session, now);
        rejectIfExpired(session, now);

        UserAccount account = userDirectory.findById(session.userId()).orElse(null);
        if (account == null || !account.status().isActive()) {
            // 用户被删除或禁用：令牌族整体作废，避免它继续换发新令牌
            refreshSessionStore.revokeFamily(UUID.fromString(session.familyId()), REASON_USER_DISABLED, now);
            if (account != null) {
                authAuditRecorder.record(AuthAuditEvent.USER_DISABLED, account.username(), account.publicId());
            }
            throw invalidTokenError();
        }

        Instant idleExpiresAt = min(now.plus(properties.getRefresh().getIdleTtl()), session.absoluteExpiresAt());
        UUID familyId = UUID.fromString(session.familyId());
        IssuedRefreshToken issued = issue(account.id(), familyId, session.absoluteExpiresAt(), idleExpiresAt);
        refreshSessionStore.markRotated(session.id(), issued.sessionId(), now);
        return new RefreshedSession(account, familyId, issued.rawToken(), issued.expiresAt());
    }

    /**
     * 撤销当前会话（退出登录）。
     *
     * <p>幂等：令牌缺失、无效或已撤销时都不报错，让客户端无论状态如何都能完成退出。</p>
     *
     * @param rawToken 客户端出示的令牌明文，可为 {@code null}
     */
    @Transactional
    public void revoke(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            return;
        }
        Instant now = Instant.now();
        refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken))
                .filter(session -> !session.isRevoked())
                .ifPresent(session -> {
                    refreshSessionStore.revoke(session.id(), REASON_LOGOUT, now);
                    recordForUser(AuthAuditEvent.LOGOUT, session.userId());
                });
    }

    /**
     * 清理过期已久的历史会话。
     *
     * @return 删除行数
     */
    @Transactional
    public int purgeExpired() {
        return refreshSessionStore.deleteExpiredBefore(Instant.now().minus(PURGE_RETENTION));
    }

    private IssuedRefreshToken issue(Long userId, UUID familyId, Instant absoluteExpiresAt, Instant idleExpiresAt) {
        String rawToken = RefreshTokens.generate();
        RefreshSession created = refreshSessionStore.create(new RefreshSessionStore.RefreshSessionDraft(
                userId, familyId, RefreshTokens.hash(rawToken), absoluteExpiresAt, idleExpiresAt));
        return new IssuedRefreshToken(created.id(), familyId, rawToken, absoluteExpiresAt);
    }

    private RefreshSession lockSession(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            throw invalidTokenError();
        }
        return refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken))
                .orElseThrow(RefreshSessionService::invalidTokenError);
    }

    /**
     * 处理「令牌已被撤销」：区分并发轮换、主动退出与真实重放。
     */
    private void rejectIfRevoked(RefreshSession session, Instant now) {
        if (!session.isRevoked()) {
            return;
        }
        if (!session.isRotated() || isWithinRotationGrace(session, now)) {
            // 主动退出过的会话，或并发刷新里慢一步的请求：只拒绝，不牵连整族
            throw invalidTokenError();
        }
        refreshSessionStore.revokeFamily(UUID.fromString(session.familyId()), REASON_REPLAY, now);
        // 真实重放（已超出宽限期）：属于安全事件，记录用户名与定位信息便于排查
        recordForUser(AuthAuditEvent.REFRESH_REPLAY, session.userId());
        throw invalidTokenError();
    }

    /** 审计按内部主键回查用户；用户已不存在时无法写入用户名，跳过该事件。 */
    private void recordForUser(AuthAuditEvent event, Long userId) {
        userDirectory.findById(userId)
                .ifPresent(account -> authAuditRecorder.record(event, account.username(), account.publicId()));
    }

    private boolean isWithinRotationGrace(RefreshSession session, Instant now) {
        return !now.isAfter(session.revokedAt().plus(properties.getRefresh().getRotationGrace()));
    }

    private void rejectIfExpired(RefreshSession session, Instant now) {
        if (now.isAfter(session.idleExpiresAt()) || now.isAfter(session.absoluteExpiresAt())) {
            refreshSessionStore.revoke(session.id(), REASON_EXPIRED, now);
            throw invalidTokenError();
        }
    }

    private static Instant min(Instant candidate, Instant limit) {
        return candidate.isBefore(limit) ? candidate : limit;
    }

    /** 对外接口只拿到令牌 {@code sub}，会话表按内部主键操作，因此先回查一次用户。 */
    private Long requireUserId(String publicId) {
        return userDirectory.findByPublicId(publicId)
                .map(UserAccount::id)
                .orElseThrow(RefreshSessionService::invalidTokenError);
    }

    /** 路径参数是客户端输入，格式非法属于参数错误而不是「会话不存在」。 */
    private static UUID parseFamilyId(String familyId) {
        try {
            return UUID.fromString(familyId);
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "会话标识格式不正确");
        }
    }

    private static SessionResponse toSessionResponse(RefreshSessionFamily family, String currentFamilyId) {
        boolean isCurrent = currentFamilyId != null
                && !currentFamilyId.isBlank()
                && currentFamilyId.equalsIgnoreCase(family.familyId());
        return new SessionResponse(
                family.familyId(),
                family.createdAt(),
                family.lastUsedAt(),
                family.idleExpiresAt(),
                family.absoluteExpiresAt(),
                isCurrent);
    }

    private static BusinessException invalidTokenError() {
        return new BusinessException(CommonErrorCode.UNAUTHORIZED, "登录状态已失效，请重新登录");
    }

    /**
     * 新签发的令牌。
     *
     * @param sessionId 会话主键
     * @param familyId  令牌族标识，访问令牌的 {@code sid} claim 取自该值
     * @param rawToken  明文令牌，只返回给客户端一次
     * @param expiresAt 绝对过期时间
     */
    public record IssuedRefreshToken(Long sessionId, UUID familyId, String rawToken, Instant expiresAt) {
    }

    /**
     * 轮换结果。
     *
     * @param account   令牌归属用户，用于签发新访问令牌
     * @param familyId  令牌族标识，访问令牌的 {@code sid} claim 取自该值
     * @param rawToken  新令牌明文
     * @param expiresAt 绝对过期时间
     */
    public record RefreshedSession(UserAccount account, UUID familyId, String rawToken, Instant expiresAt) {
    }
}
