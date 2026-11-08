package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.identity.application.RefreshSessionStore;
import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshSessionFamily;
import com.example.agent.identity.domain.RefreshTokens;
import com.example.agent.identity.domain.UserAccount;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * V3 迁移与刷新会话仓储的持久层测试。
 *
 * <p>必须连真实 PostgreSQL：{@code FOR UPDATE} 行锁、{@code family_id} 的 UUID 转换、
 * 外键约束与 {@code revoked_at IS NULL} 的幂等更新都无法用内存实现等价验证。</p>
 */
@SpringBootTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@Testcontainers
class RefreshSessionPersistenceTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private final RefreshSessionStore refreshSessionStore;

    private final UserDirectory userDirectory;

    @Autowired
    RefreshSessionPersistenceTests(RefreshSessionStore refreshSessionStore, UserDirectory userDirectory) {
        this.refreshSessionStore = refreshSessionStore;
        this.userDirectory = userDirectory;
    }

    @Test
    void create_shouldPersistHashedTokenAndBeLockable() {
        UserAccount admin = adminAccount();
        String rawToken = "persisted-token-" + UUID.randomUUID();
        Instant absoluteExpiresAt = Instant.now().plus(Duration.ofDays(30));

        RefreshSession created = refreshSessionStore.create(new RefreshSessionStore.RefreshSessionDraft(
                admin.id(), UUID.randomUUID(), RefreshTokens.hash(rawToken), absoluteExpiresAt, absoluteExpiresAt));

        assertThat(created.id()).isPositive();
        // 只存摘要：明文令牌不会出现在任何列里
        assertThat(created.tokenHash()).isEqualTo(RefreshTokens.hash(rawToken));
        RefreshSession loaded = refreshSessionStore.lockByTokenHash(RefreshTokens.hash(rawToken)).orElseThrow();
        assertThat(loaded.userId()).isEqualTo(admin.id());
        assertThat(loaded.familyId()).isEqualTo(created.familyId());
        assertThat(loaded.isRevoked()).isFalse();
    }

    @Test
    void markRotated_shouldLinkSuccessorAndRevokeOldSession() {
        UserAccount admin = adminAccount();
        UUID familyId = UUID.randomUUID();
        RefreshSession oldSession = createSession(admin.id(), familyId, "old-token");
        RefreshSession newSession = createSession(admin.id(), familyId, "new-token");

        refreshSessionStore.markRotated(oldSession.id(), newSession.id(), Instant.now());

        RefreshSession reloaded = refreshSessionStore.lockByTokenHash(oldSession.tokenHash()).orElseThrow();
        assertThat(reloaded.revokedReason()).isEqualTo("rotated");
        assertThat(reloaded.isRotated()).isTrue();
        assertThat(reloaded.replacedById()).isEqualTo(newSession.id());
        // 后继会话仍然有效，否则正常用户会被自己的轮换踢下线
        assertThat(refreshSessionStore.lockByTokenHash(newSession.tokenHash()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void revokeFamily_shouldRevokeEveryActiveSessionInFamily() {
        UserAccount admin = adminAccount();
        UUID familyId = UUID.randomUUID();
        createSession(admin.id(), familyId, "first-token");
        createSession(admin.id(), familyId, "second-token");
        RefreshSession otherFamily = createSession(admin.id(), UUID.randomUUID(), "other-token");

        int revoked = refreshSessionStore.revokeFamily(familyId, "replay", Instant.now());

        assertThat(revoked).isEqualTo(2);
        assertThat(refreshSessionStore.lockByTokenHash(otherFamily.tokenHash()).orElseThrow().isRevoked()).isFalse();
    }

    @Test
    void revokeAllExceptFamily_shouldRevokeOtherFamiliesOfSameUserOnly() {
        UserAccount owner = createUser("multi-device");
        UUID currentFamilyId = UUID.randomUUID();
        RefreshSession currentDevice = createSession(owner.id(), currentFamilyId, "current-token");
        RefreshSession otherDevice = createSession(owner.id(), UUID.randomUUID(), "other-token");
        RefreshSession otherUserSession = createSession(
                userDirectory.findByUsername("demo").orElseThrow().id(), UUID.randomUUID(), "demo-token");

        int revoked = refreshSessionStore.revokeAllExceptFamily(
                owner.id(), currentFamilyId, "password_change", Instant.now());

        assertThat(revoked).isEqualTo(1);
        assertThat(refreshSessionStore.lockByTokenHash(currentDevice.tokenHash()).orElseThrow().isRevoked()).isFalse();
        assertThat(refreshSessionStore.lockByTokenHash(otherDevice.tokenHash()).orElseThrow().revokedReason())
                .isEqualTo("password_change");
        assertThat(refreshSessionStore.lockByTokenHash(otherUserSession.tokenHash()).orElseThrow().isRevoked())
                .isFalse();
    }

    @Test
    void listFamilies_shouldCollapseChainAndExcludeRevokedFamilies() {
        UserAccount owner = createUser("session-list");
        UUID activeFamily = UUID.randomUUID();
        RefreshSession firstRow = createSession(owner.id(), activeFamily, "active-first");
        RefreshSession rotatedRow = createSession(owner.id(), activeFamily, "active-rotated");
        refreshSessionStore.markRotated(firstRow.id(), rotatedRow.id(), Instant.now());

        UUID revokedFamily = UUID.randomUUID();
        createSession(owner.id(), revokedFamily, "revoked");
        assertThat(refreshSessionStore.revokeFamilyForUser(owner.id(), revokedFamily, "logout", Instant.now()))
                .isEqualTo(1);

        List<RefreshSessionFamily> families = refreshSessionStore.listFamilies(owner.id(), 0, 20);

        assertThat(families).hasSize(1);
        RefreshSessionFamily family = families.get(0);
        assertThat(family.familyId()).isEqualTo(activeFamily.toString());
        // 轮换链只算一台设备，最近使用时间来自被轮换的旧行
        assertThat(family.lastUsedAt()).isNotNull();
        assertThat(family.idleExpiresAt()).isAfter(Instant.now());
        assertThat(family.absoluteExpiresAt()).isAfter(Instant.now());
        assertThat(refreshSessionStore.countFamilies(owner.id())).isEqualTo(1);
    }

    @Test
    void revokeAllForUser_shouldOnlyRevokeSessionsOfTargetUser() {
        UserAccount owner = createUser("logout-all");
        UserAccount other = createUser("logout-all-other");
        createSession(owner.id(), UUID.randomUUID(), "owner-first");
        createSession(owner.id(), UUID.randomUUID(), "owner-second");
        RefreshSession otherSession = createSession(other.id(), UUID.randomUUID(), "other-user");

        int revoked = refreshSessionStore.revokeAllForUser(owner.id(), "logout", Instant.now());

        assertThat(revoked).isEqualTo(2);
        assertThat(refreshSessionStore.lockByTokenHash(otherSession.tokenHash()).orElseThrow().isRevoked())
                .isFalse();
        assertThat(refreshSessionStore.countFamilies(owner.id())).isZero();
    }

    @Test
    void revokeFamilyForUser_shouldRejectFamilyOfAnotherUser() {
        UserAccount owner = createUser("family-owner");
        UserAccount other = createUser("family-other");
        UUID familyId = UUID.randomUUID();
        RefreshSession otherSession = createSession(other.id(), familyId, "other-family");

        assertThat(refreshSessionStore.revokeFamilyForUser(owner.id(), familyId, "logout", Instant.now()))
                .isZero();
        assertThat(refreshSessionStore.lockByTokenHash(otherSession.tokenHash()).orElseThrow().isRevoked())
                .isFalse();
    }

    @Test
    void revoke_shouldBeIdempotent() {
        UserAccount admin = adminAccount();
        RefreshSession session = createSession(admin.id(), UUID.randomUUID(), "logout-token");

        assertThat(refreshSessionStore.revoke(session.id(), "logout", Instant.now())).isEqualTo(1);
        // 第二次撤销不再改动数据，避免并发场景下覆盖撤销原因
        assertThat(refreshSessionStore.revoke(session.id(), "logout", Instant.now())).isZero();
    }

    @Test
    void deleteExpiredBefore_shouldRemoveOnlyRowsPastCutoff() {
        UserAccount admin = adminAccount();
        RefreshSession expired = refreshSessionStore.create(new RefreshSessionStore.RefreshSessionDraft(
                admin.id(), UUID.randomUUID(), RefreshTokens.hash("expired-" + UUID.randomUUID()),
                Instant.now().minus(Duration.ofDays(40)), Instant.now().minus(Duration.ofDays(40))));
        createSession(admin.id(), UUID.randomUUID(), "active-token");

        int deleted = refreshSessionStore.deleteExpiredBefore(Instant.now().minus(Duration.ofDays(7)));

        assertThat(deleted).isEqualTo(1);
        assertThat(refreshSessionStore.lockByTokenHash(expired.tokenHash())).isEmpty();
    }

    private UserAccount adminAccount() {
        return userDirectory.findByUsername("admin").orElseThrow();
    }

    /** 新建独立用户，避免与同库里其他用例的会话互相干扰。 */
    private UserAccount createUser(String prefix) {
        return userDirectory.create(prefix + "-" + UUID.randomUUID(), "$2a$10$placeholder", List.of("USER"));
    }

    private RefreshSession createSession(Long userId, UUID familyId, String rawTokenPrefix) {
        Instant absoluteExpiresAt = Instant.now().plus(Duration.ofDays(30));
        return refreshSessionStore.create(new RefreshSessionStore.RefreshSessionDraft(
                userId,
                familyId,
                RefreshTokens.hash(rawTokenPrefix + "-" + UUID.randomUUID()),
                absoluteExpiresAt,
                absoluteExpiresAt));
    }
}
