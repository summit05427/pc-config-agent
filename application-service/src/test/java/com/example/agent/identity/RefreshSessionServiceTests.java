package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.catchThrowableOfType;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.application.RefreshSessionService;
import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshTokens;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.web.dto.SessionResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.AppSecurityProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.support.InMemoryRefreshSessionStore;
import com.example.agent.support.InMemoryUserDirectory;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 刷新会话服务单元测试：覆盖轮换、双重过期、重放检测与清理。
 *
 * <p>用内存仓储与真实时钟，重点验证「什么时候必须拒绝、拒绝时是否牵连整族」这些规则；
 * SQL 与行锁行为由持久层测试负责。</p>
 */
class RefreshSessionServiceTests {

    private static final String PASSWORD_HASH = "$2a$10$placeholder";

    private final InMemoryUserDirectory userDirectory = new InMemoryUserDirectory();
    private final InMemoryRefreshSessionStore refreshSessionStore = new InMemoryRefreshSessionStore();
    private final AppSecurityProperties properties = new AppSecurityProperties();
    /** 审计在本测试中不关心，用空实现避免引入数据库。 */
    private final AuthAuditRecorder authAuditRecorder = new AuthAuditRecorder(entry -> { });
    private final RefreshSessionService refreshSessionService =
            new RefreshSessionService(refreshSessionStore, userDirectory, properties, authAuditRecorder);

    private UserAccount account;

    @BeforeEach
    void setUp() {
        account = userDirectory.create("admin", PASSWORD_HASH, List.of("USER"));
    }

    @Test
    void start_shouldCreateSessionWithIdleAndAbsoluteExpiry() {
        RefreshSessionService.IssuedRefreshToken issued = refreshSessionService.start(account.id());

        RefreshSession session = refreshSessionStore.findById(issued.sessionId()).orElseThrow();
        assertThat(session.userId()).isEqualTo(account.id());
        assertThat(session.isRevoked()).isFalse();
        // 绝对期限 30 天：Cookie 的 Max-Age 以此为准
        assertThat(Duration.between(Instant.now(), issued.expiresAt())).isCloseTo(
                properties.getRefresh().getAbsoluteTtl(), Duration.ofMinutes(1));
        // 闲置期限不超过绝对期限
        assertThat(session.idleExpiresAt()).isBeforeOrEqualTo(session.absoluteExpiresAt());
        assertThat(session.tokenHash()).isEqualTo(RefreshTokens.hash(issued.rawToken()));
        // 族标识必须向外暴露，访问令牌的 sid claim 依赖它
        assertThat(issued.familyId().toString()).isEqualTo(session.familyId());
    }

    @Test
    void rotate_shouldIssueNewTokenAndRevokeOldTokenInSameFamily() {
        RefreshSessionService.IssuedRefreshToken first = refreshSessionService.start(account.id());

        RefreshSessionService.RefreshedSession rotated = refreshSessionService.rotate(first.rawToken());

        assertThat(rotated.account().id()).isEqualTo(account.id());
        assertThat(rotated.rawToken()).isNotEqualTo(first.rawToken());
        // 旧会话被标记为已轮换，并指向新会话
        RefreshSession oldSession = refreshSessionStore.findById(first.sessionId()).orElseThrow();
        assertThat(oldSession.revokedReason()).isEqualTo("rotated");
        assertThat(oldSession.replacedById()).isNotNull();
        // 新令牌仍属于同一族，且绝对过期时间未被延长
        RefreshSession newSession = refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rotated.rawToken())).orElseThrow();
        assertThat(newSession.familyId()).isEqualTo(oldSession.familyId());
        assertThat(newSession.absoluteExpiresAt()).isEqualTo(oldSession.absoluteExpiresAt());
        // 刷新签发的访问令牌同样带 sid，必须指向同一个族
        assertThat(rotated.familyId().toString()).isEqualTo(oldSession.familyId());
    }

    @Test
    void revokeAllExceptFamily_shouldKeepCurrentFamilyAndRevokeOtherDevices() {
        RefreshSessionService.IssuedRefreshToken currentDevice = refreshSessionService.start(account.id());
        RefreshSessionService.IssuedRefreshToken otherDevice = refreshSessionService.start(account.id());
        UserAccount otherUser = userDirectory.create("other", PASSWORD_HASH, List.of("USER"));
        RefreshSessionService.IssuedRefreshToken otherUserSession = refreshSessionService.start(otherUser.id());

        int revoked = refreshSessionService.revokeAllExceptFamily(account.id(), currentDevice.familyId());

        assertThat(revoked).isEqualTo(1);
        assertThat(refreshSessionStore.findById(currentDevice.sessionId()).orElseThrow().isRevoked()).isFalse();
        assertThat(refreshSessionStore.findById(otherDevice.sessionId()).orElseThrow().revokedReason())
                .isEqualTo("password_change");
        // 撤销范围严格限定在同一用户内
        assertThat(refreshSessionStore.findById(otherUserSession.sessionId()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void listFamilies_shouldCollapseRotationChainIntoOneDeviceAndMarkCurrent() {
        RefreshSessionService.IssuedRefreshToken currentDevice = refreshSessionService.start(account.id());
        // 轮换一次：同一族产生第二行，设备列表仍只应出现一条
        refreshSessionService.rotate(currentDevice.rawToken());
        RefreshSessionService.IssuedRefreshToken otherDevice = refreshSessionService.start(account.id());

        PageResult<SessionResponse> page = refreshSessionService.listFamilies(
                account.publicId(), currentDevice.familyId().toString(), new PageQuery());

        assertThat(page.total()).isEqualTo(2);
        assertThat(page.list()).hasSize(2);
        assertThat(page.list()).filteredOn(SessionResponse::current).hasSize(1);
        SessionResponse currentRow = page.list().stream()
                .filter(SessionResponse::current)
                .findFirst()
                .orElseThrow();
        assertThat(currentRow.familyId()).isEqualTo(currentDevice.familyId().toString());
        // 轮换时旧行记录了使用时间，聚合后的 lastUsedAt 不应为空
        assertThat(currentRow.lastUsedAt()).isNotNull();
        assertThat(page.list()).extracting(SessionResponse::familyId)
                .containsExactlyInAnyOrder(currentDevice.familyId().toString(), otherDevice.familyId().toString());
    }

    @Test
    void listFamilies_shouldMarkNothingCurrent_whenTokenHasNoSessionClaim() {
        refreshSessionService.start(account.id());
        refreshSessionService.start(account.id());

        PageResult<SessionResponse> page = refreshSessionService.listFamilies(account.publicId(), null, new PageQuery());

        // 存量令牌没有 sid：列表照常返回，但全部 current=false，不报错
        assertThat(page.list()).hasSize(2).allMatch(session -> !session.current());
    }

    @Test
    void listFamilies_shouldPaginateDevices() {
        refreshSessionService.start(account.id());
        refreshSessionService.start(account.id());
        refreshSessionService.start(account.id());
        PageQuery query = new PageQuery();
        query.setPage(2);
        query.setSize(2);

        PageResult<SessionResponse> page = refreshSessionService.listFamilies(account.publicId(), null, query);

        assertThat(page.total()).isEqualTo(3);
        assertThat(page.page()).isEqualTo(2);
        assertThat(page.size()).isEqualTo(2);
        assertThat(page.list()).hasSize(1);
    }

    @Test
    void revokeFamily_shouldRejectCurrentDevice() {
        RefreshSessionService.IssuedRefreshToken currentDevice = refreshSessionService.start(account.id());

        BusinessException exception = catchThrowableOfType(
                () -> refreshSessionService.revokeFamily(
                        account.publicId(), currentDevice.familyId().toString(), currentDevice.familyId().toString()),
                BusinessException.class);

        assertThat(exception.getErrorCode().code()).isEqualTo(30002);
        assertThat(refreshSessionStore.findById(currentDevice.sessionId()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void revokeFamily_shouldRejectFamilyOfAnotherUser() {
        UserAccount otherUser = userDirectory.create("other-session", PASSWORD_HASH, List.of("USER"));
        RefreshSessionService.IssuedRefreshToken otherUserDevice = refreshSessionService.start(otherUser.id());

        BusinessException exception = catchThrowableOfType(
                () -> refreshSessionService.revokeFamily(
                        account.publicId(), otherUserDevice.familyId().toString(), null),
                BusinessException.class);

        assertThat(exception.getErrorCode().code()).isEqualTo(40105);
        // 他人的族不受影响
        assertThat(refreshSessionStore.findById(otherUserDevice.sessionId()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void revokeFamily_shouldRevokeOnlyTargetDevice() {
        RefreshSessionService.IssuedRefreshToken currentDevice = refreshSessionService.start(account.id());
        RefreshSessionService.IssuedRefreshToken otherDevice = refreshSessionService.start(account.id());

        refreshSessionService.revokeFamily(
                account.publicId(), otherDevice.familyId().toString(), currentDevice.familyId().toString());

        assertThat(refreshSessionStore.findById(otherDevice.sessionId()).orElseThrow().revokedReason())
                .isEqualTo("logout");
        assertThat(refreshSessionStore.findById(currentDevice.sessionId()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void revokeFamily_shouldRejectMalformedIdentifier() {
        BusinessException exception = catchThrowableOfType(
                () -> refreshSessionService.revokeFamily(account.publicId(), "not-a-uuid", null),
                BusinessException.class);

        assertThat(exception.getErrorCode().code()).isEqualTo(10001);
    }

    @Test
    void logoutAll_shouldRevokeEveryFamilyOfCurrentUser() {
        RefreshSessionService.IssuedRefreshToken first = refreshSessionService.start(account.id());
        RefreshSessionService.IssuedRefreshToken second = refreshSessionService.start(account.id());
        UserAccount otherUser = userDirectory.create("other-logout", PASSWORD_HASH, List.of("USER"));
        RefreshSessionService.IssuedRefreshToken otherUserSession = refreshSessionService.start(otherUser.id());

        int revoked = refreshSessionService.logoutAll(account.publicId());

        assertThat(revoked).isEqualTo(2);
        assertThat(refreshSessionStore.findById(first.sessionId()).orElseThrow().revokedReason()).isEqualTo("logout");
        assertThat(refreshSessionStore.findById(second.sessionId()).orElseThrow().revokedReason()).isEqualTo("logout");
        assertThat(refreshSessionStore.findById(otherUserSession.sessionId()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void rotate_shouldRejectUnknownToken() {
        assertThatThrownBy(() -> refreshSessionService.rotate("unknown-token"))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void rotate_shouldRejectBlankToken() {
        assertThatThrownBy(() -> refreshSessionService.rotate("  "))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void rotate_shouldRejectAndRevokeSession_whenIdleExpired() {
        String rawToken = "expired-token";
        seedSession(account.id(), rawToken, Instant.now().minus(Duration.ofDays(40)), Instant.now().minus(Duration.ofDays(9)));

        assertThatThrownBy(() -> refreshSessionService.rotate(rawToken))
                .isInstanceOf(BusinessException.class);
        RefreshSession session = refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken)).orElseThrow();
        assertThat(session.revokedReason()).isEqualTo("expired");
    }

    @Test
    void rotate_shouldRevokeWholeFamily_whenRotatedTokenReplayedAfterGrace() {
        String rawToken = "replayed-token";
        seedSession(account.id(), rawToken, Instant.now().plus(Duration.ofDays(1)), Instant.now().plus(Duration.ofDays(1)));
        // 模拟「该令牌已轮换，且早已超过宽限期」：这是被窃取后重放的典型特征
        RefreshSession seeded = refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken)).orElseThrow();
        refreshSessionStore.markRotated(seeded.id(), seeded.id() + 1, Instant.now().minus(Duration.ofMinutes(10)));
        refreshSessionStore.seed(new RefreshSession(
                seeded.id() + 1, account.id(), seeded.familyId(), "successor-hash", Instant.now(), null,
                Instant.now().plus(Duration.ofDays(1)), Instant.now().plus(Duration.ofDays(1)), null, null, null));

        assertThatThrownBy(() -> refreshSessionService.rotate(rawToken))
                .isInstanceOf(BusinessException.class);

        // 整族作废：后继令牌也不能再用
        assertThat(refreshSessionStore.findAll())
                .allMatch(session -> session.revokedReason() != null && session.isRevoked());
    }

    @Test
    void rotate_shouldNotRevokeFamily_whenReplayIsWithinRotationGrace() {
        String rawToken = "concurrent-token";
        seedSession(account.id(), rawToken, Instant.now().plus(Duration.ofDays(1)), Instant.now().plus(Duration.ofDays(1)));
        RefreshSession seeded = refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken)).orElseThrow();
        // 刚被轮换，属于两个标签页同时刷新的并发冲突，不应牵连整族
        refreshSessionStore.markRotated(seeded.id(), seeded.id() + 1, Instant.now());

        assertThatThrownBy(() -> refreshSessionService.rotate(rawToken))
                .isInstanceOf(BusinessException.class);
        assertThat(refreshSessionStore.findAll()).noneMatch(session -> "replay".equals(session.revokedReason()));
    }

    @Test
    void rotate_shouldRevokeWholeFamily_whenUserNoLongerExists() {
        String rawToken = "orphan-token";
        seedSession(9999L, rawToken, Instant.now().plus(Duration.ofDays(1)), Instant.now().plus(Duration.ofDays(1)));

        assertThatThrownBy(() -> refreshSessionService.rotate(rawToken))
                .isInstanceOf(BusinessException.class);
        assertThat(refreshSessionStore.findAll())
                .allMatch(session -> "user_disabled".equals(session.revokedReason()));
    }

    @Test
    void revoke_shouldBeIdempotentAndIgnoreMissingToken() {
        RefreshSessionService.IssuedRefreshToken issued = refreshSessionService.start(account.id());

        refreshSessionService.revoke(null);
        refreshSessionService.revoke(issued.rawToken());
        refreshSessionService.revoke(issued.rawToken());

        RefreshSession session = refreshSessionStore.findById(issued.sessionId()).orElseThrow();
        assertThat(session.revokedReason()).isEqualTo("logout");
        assertThatThrownBy(() -> refreshSessionService.rotate(issued.rawToken()))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void purgeExpired_shouldDeleteOnlySessionsPastRetention() {
        seedSession(account.id(), "old-token", Instant.now().minus(Duration.ofDays(20)), Instant.now().minus(Duration.ofDays(20)));
        refreshSessionService.start(account.id());

        int deleted = refreshSessionService.purgeExpired();

        assertThat(deleted).isEqualTo(1);
        assertThat(refreshSessionStore.findAll()).hasSize(1);
    }

    private void seedSession(Long userId, String rawToken, Instant absoluteExpiresAt, Instant idleExpiresAt) {
        refreshSessionStore.seed(new RefreshSession(
                refreshSessionStore.findAll().size() + 1L,
                userId,
                UUID.randomUUID().toString(),
                RefreshTokens.hash(rawToken),
                Instant.now(),
                null,
                absoluteExpiresAt,
                idleExpiresAt,
                null,
                null,
                null));
    }
}
