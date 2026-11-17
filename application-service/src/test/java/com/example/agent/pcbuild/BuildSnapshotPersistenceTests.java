package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.BuildSolverVersion;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.shared.error.BusinessException;
import java.util.EnumMap;
import java.util.Map;
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

    /** 兼容且八件均有有效报价的基线组合。 */
    private static final Map<HardwareCategory, String> COMPLETE_HARDWARE_IDS = Map.of(
            HardwareCategory.CPU, "cpu-amd-ryzen-7-9800x3d",
            HardwareCategory.MOTHERBOARD, "motherboard-msi-mag-b850m-mortar-wifi",
            HardwareCategory.MEMORY, "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-5600-cl40",
            HardwareCategory.GPU, "gpu-geforce-rtx-5070-ti-16gb-563955",
            HardwareCategory.PSU, "psu-segotep-gm750w",
            HardwareCategory.CASE, "case-lian-li-lancool-205-mesh",
            HardwareCategory.COOLER, "cooler-thermalright-peerless-assassin",
            HardwareCategory.STORAGE, "storage-kingston-nv3-1-tb-591379");

    @Autowired
    private BuildSolveService buildSolveService;

    @Autowired
    private BuildSnapshotRepository buildSnapshotRepository;

    @Test
    void composedBuild_shouldBeReadableByOwnerWithAllComponents() {
        UUID userId = UUID.randomUUID();
        BuildResult result = buildSolveService.composeAndSnapshot(userId, completeIds(), null);

        BuildResultResponse response = buildSolveService.requireBuild(userId, result.buildId());

        assertThat(response.buildId()).isEqualTo(result.buildId());
        assertThat(response.components()).hasSize(8);
        assertThat(response.totalPriceFen()).isEqualTo(result.totalPriceFen());
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
        BuildResult result = buildSolveService.composeAndSnapshot(userId, completeIds(), null);

        BuildSnapshot snapshot = buildSnapshotRepository
                .findByIdAndUserId(result.buildId(), userId)
                .orElseThrow();
        assertThat(snapshot.requirementsSnapshot())
                .contains("\"workloadProfile\"")
                .contains("\"renderMode\"")
                .contains("\"scoringVersion\"");
    }

    @Test
    void snapshot_shouldNotBeReadableByAnotherUser() {
        UUID owner = UUID.randomUUID();
        BuildResult result = buildSolveService.composeAndSnapshot(owner, completeIds(), null);

        assertThatThrownBy(() -> buildSolveService.requireBuild(UUID.randomUUID(), result.buildId()))
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

    private static Map<HardwareCategory, String> completeIds() {
        return new EnumMap<>(COMPLETE_HARDWARE_IDS);
    }
}
