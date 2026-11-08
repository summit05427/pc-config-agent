package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.UserAccount;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * V2 迁移与用户仓储的持久层测试。
 *
 * <p>必须连真实 PostgreSQL：UUID 默认值、唯一约束与 {@code ::uuid} 参数转换
 * 都无法用内存数据库等价验证，因此使用与生产一致的镜像版本。</p>
 */
@SpringBootTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@Testcontainers
class UserPersistenceTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private final UserDirectory userDirectory;

    @Autowired
    UserPersistenceTests(UserDirectory userDirectory) {
        this.userDirectory = userDirectory;
    }

    @Test
    void migration_shouldSeedBootstrapAccountsWithPublicId() {
        UserAccount admin = userDirectory.findByUsername("admin").orElseThrow();

        assertThat(admin.id()).isPositive();
        assertThat(UUID.fromString(admin.publicId())).isNotNull();
        assertThat(admin.roles()).containsExactly("ADMIN");
        assertThat(admin.status().isActive()).isTrue();
        // 口令必须落库为摘要，不能是明文
        assertThat(admin.passwordHash()).startsWith("$2");
        assertThat(userDirectory.findByPublicId(admin.publicId())).isPresent();
        assertThat(userDirectory.findByUsername("demo")).isPresent();
    }

    @Test
    void findByUsername_shouldReturnEmpty_whenUserDoesNotExist() {
        assertThat(userDirectory.findByUsername("missing-user")).isEmpty();
    }

    @Test
    void findByPublicId_shouldReturnEmpty_whenUserDoesNotExist() {
        assertThat(userDirectory.findByPublicId(UUID.randomUUID().toString())).isEmpty();
    }

    @Test
    void create_shouldRejectDuplicateUsername() {
        assertThatThrownBy(() -> userDirectory.create("admin", "$2a$10$placeholder", List.of("USER")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void create_shouldPersistNewUserWithGeneratedPublicId() {
        UserAccount created = userDirectory.create("integration-user", "$2a$10$placeholder", List.of("USER", "AUDITOR"));

        UserAccount reloaded = userDirectory.findByUsername("integration-user").orElseThrow();
        assertThat(reloaded.publicId()).isEqualTo(created.publicId());
        assertThat(reloaded.roles()).containsExactly("USER", "AUDITOR");
    }

    @Test
    void updatePasswordHash_shouldReplaceStoredHash() {
        UserAccount admin = userDirectory.findByUsername("admin").orElseThrow();
        String originalHash = admin.passwordHash();

        userDirectory.updatePasswordHash(admin.publicId(), "$2a$10$updatedplaceholder");

        assertThat(userDirectory.findByPublicId(admin.publicId()).orElseThrow().passwordHash())
                .isEqualTo("$2a$10$updatedplaceholder");
        // 恢复原摘要，避免影响同一容器内后续用例的登录
        userDirectory.updatePasswordHash(admin.publicId(), originalHash);
    }
}
