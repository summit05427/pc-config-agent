package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.SolveExecutionResult;
import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.BuildSolverVersion;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.Preference;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.shared.error.BusinessException;
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
 * 方案快照持久化与归属测试：真实 PostgreSQL + Flyway V24。
 */
@SpringBootTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@Testcontainers
class BuildSnapshotPersistenceTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired
    private BuildSolveService buildSolveService;

    @Autowired
    private BuildSnapshotRepository buildSnapshotRepository;

    @Test
    void solvedBuild_shouldBeReadableByOwnerWithAllComponents() {
        UUID userId = UUID.randomUUID();
        SolveExecutionResult execution = buildSolveService.solve(userId, requirements());
        assertThat(execution.isSolved()).isTrue();

        UUID buildId = execution.build().buildId();
        BuildResultResponse response = buildSolveService.requireBuild(userId, buildId);

        assertThat(response.buildId()).isEqualTo(buildId);
        assertThat(response.components()).hasSize(8);
        assertThat(response.totalPriceFen()).isEqualTo(execution.build().totalPriceFen());
        assertThat(response.verifiedOfferCount() + response.demoOfferCount()).isEqualTo(8);
        // 九条兼容性规则（原八条 + 内存条数）。
        assertThat(response.compatibilityReport().checks()).hasSize(9);
        assertThat(response.compatibilityRuleVersion()).isEqualTo("pc-compat-2.0.0");
        // 版本号随实现升级，断言直接引用常量，避免每次升级都要改测试。
        assertThat(response.solverVersion()).isEqualTo(BuildSolverVersion.SOLVER_VERSION);
        assertThat(response.scoringVersion()).isEqualTo("pc-scoring-1.0.0");
        assertThat(response.requirements().workloadProfile()).isNotNull();
        assertThat(response.offerDataStatus()).isEqualTo("PLATFORM_OBSERVED_ONLY");
        assertThat(response.createdAt()).isNotNull();
        // 快照读取时按组件与跑分重建逐件理由，历史方案不因读取路径丢失解释。
        assertThat(response.componentReasons()).hasSize(8);
        assertThat(response.reasonSummary()).isNotBlank();
    }

    @Test
    void requirementsSnapshot_shouldCarryProfileRenderModeAndScoringVersion() {
        UUID userId = UUID.randomUUID();
        SolveExecutionResult execution = buildSolveService.solve(userId, requirements());
        assertThat(execution.isSolved()).isTrue();

        BuildSnapshot snapshot = buildSnapshotRepository
                .findByIdAndUserId(execution.build().buildId(), userId)
                .orElseThrow();
        assertThat(snapshot.requirementsSnapshot())
                .contains("\"workloadProfile\"")
                .contains("\"renderMode\"")
                .contains("\"scoringVersion\"");
    }

    @Test
    void requirementsSnapshot_shouldCarryPreference() {
        UUID userId = UUID.randomUUID();
        BuildRequirements valueRequirements = new BuildRequirements(
                2_000_000L, BuildScenario.GAMING, null, null, false,
                null, null, null, Preference.VALUE);
        SolveExecutionResult execution = buildSolveService.solve(userId, valueRequirements);
        assertThat(execution.isSolved()).isTrue();

        BuildSnapshot snapshot = buildSnapshotRepository
                .findByIdAndUserId(execution.build().buildId(), userId)
                .orElseThrow();
        // 快照按带空格的 JSON 序列化，断言空格后的值而非紧凑格式。
        assertThat(snapshot.requirementsSnapshot()).contains("\"preference\": \"VALUE\"");
    }

    @Test
    void snapshot_shouldNotBeReadableByAnotherUser() {
        UUID owner = UUID.randomUUID();
        SolveExecutionResult execution = buildSolveService.solve(owner, requirements());
        UUID buildId = execution.build().buildId();

        assertThatThrownBy(() -> buildSolveService.requireBuild(UUID.randomUUID(), buildId))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(
                        ((BusinessException) exception).getErrorCode().code()).isEqualTo(40302));
    }

    @Test
    void unknownSnapshot_shouldReturnNotFound() {
        assertThatThrownBy(() -> buildSolveService.requireBuild(UUID.randomUUID(), UUID.randomUUID()))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(
                        ((BusinessException) exception).getErrorCode().code()).isEqualTo(40302));
    }

    private BuildRequirements requirements() {
        return new BuildRequirements(2_000_000L, BuildScenario.GAMING, null, null, false);
    }
}
