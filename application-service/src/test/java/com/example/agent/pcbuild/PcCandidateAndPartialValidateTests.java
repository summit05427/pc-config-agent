package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.application.BuildResultFactory;
import com.example.agent.pcbuild.application.BuildSnapshotService;
import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.BuildSolver;
import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.application.HardwareCandidate;
import com.example.agent.pcbuild.application.HardwareCandidateService;
import com.example.agent.pcbuild.application.HardwareCatalogService;
import com.example.agent.pcbuild.application.InternalUserTokenResolver;
import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.application.port.HardwareCatalogRepository;
import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import com.example.agent.pcbuild.web.PcBuildInternalController;
import com.example.agent.pcbuild.web.dto.PartialValidateRequest;
import com.example.agent.pcbuild.web.dto.PartialValidateResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.BusinessException;
import java.time.LocalDate;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 候选决策字段与部分兼容性校验测试。
 *
 * <p>使用真实 fixture 仓储，不启 Spring 容器、不依赖数据库；报价与目录的异常分支
 * 用内存替身补齐。</p>
 */
class PcCandidateAndPartialValidateTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private static final String CPU_ID = "cpu-amd-ryzen-7-9800x3d";

    private static final String MOTHERBOARD_ID = "motherboard-msi-mag-b850m-mortar-wifi";

    /** LGA1851 主板，与 AM5 的 {@link #CPU_ID} 必然插槽不符。 */
    private static final String LGA_MOTHERBOARD_ID = "motherboard-asus-tuf-gaming-b860m-plus-wifi";

    private final JsonHardwareCatalogRepository catalogRepository =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offerRepository = new JsonOfferRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarkRepository =
            new JsonBenchmarkRepository(OBJECT_MAPPER);

    private final HardwareCatalogService catalogService =
            new HardwareCatalogService(catalogRepository);

    // ---------------------------------------------------------------- 候选字段

    @Test
    void candidates_shouldCarryCheapestUsableOfferPrice() {
        Offer expensive = offer("offer-expensive", CPU_ID, 379_900L, LocalDate.of(2099, 1, 1));
        Offer cheapest = offer("offer-cheapest", CPU_ID, 355_000L, LocalDate.of(2099, 1, 1));
        Offer expired = offer("offer-expired", CPU_ID, 100_000L, LocalDate.of(2020, 1, 1));

        List<HardwareCandidate> candidates = candidateService(
                new FixedOfferRepository(List.of(expensive, cheapest, expired)))
                .listCandidates(HardwareCategory.CPU);

        HardwareCandidate cpu = candidateOf(candidates, CPU_ID);
        // 过期报价不参与取价，最低可用报价胜出。
        assertThat(cpu.priceFen()).isEqualTo(355_000L);
        assertThat(cpu.missingFields()).isEmpty();
    }

    @Test
    void candidates_shouldReturnNullPriceWhenNoUsableOffer() {
        List<HardwareCandidate> candidates = candidateService(new FixedOfferRepository(List.of()))
                .listCandidates(HardwareCategory.CPU);

        HardwareCandidate cpu = candidateOf(candidates, CPU_ID);
        // 目录里的 price_cny 只是录入参考价，不能作为报价兜底。
        assertThat(catalogRepository.findById(CPU_ID)).isPresent();
        assertThat(cpu.priceFen()).isNull();
    }

    @Test
    void candidates_shouldExposeMissingCompatibilityFields() {
        List<HardwareCandidate> cases = candidateService(new FixedOfferRepository(List.of()))
                .listCandidates(HardwareCategory.CASE);

        assertThat(cases).isNotEmpty();
        // 夹具机箱普遍缺 max_cooler_height_mm，该字段直接决定 cooler_case_height 规则。
        assertThat(cases).anySatisfy(candidate ->
                assertThat(candidate.missingFields()).contains("max_cooler_height_mm"));
    }

    @Test
    void candidates_shouldKeepEveryCatalogEntryWithStableOrder() {
        HardwareCandidateService service = candidateService(new FixedOfferRepository(List.of()));

        List<HardwareCandidate> candidates = service.listCandidates(HardwareCategory.CPU);
        long catalogCpuCount = catalogRepository.findAll().stream()
                .filter(hardware -> hardware.category() == HardwareCategory.CPU)
                .count();

        assertThat(candidates).hasSize((int) catalogCpuCount);
        assertThat(candidates).extracting(candidate -> candidate.hardware().hardwareId())
                .isSorted();
    }

    // ------------------------------------------------------------ 部分兼容性校验

    @Test
    void partialValidate_cpuAndMotherboard_shouldPass() {
        CompatibilityReport report = service().validatePartial(Map.of(
                HardwareCategory.CPU, CPU_ID,
                HardwareCategory.MOTHERBOARD, MOTHERBOARD_ID));

        assertThat(report.checks()).hasSize(1);
        assertThat(report.checks().get(0).ruleId())
                .isEqualTo(CompatibilityRule.CPU_SOCKET_MOTHERBOARD.ruleId());
        assertThat(report.checks().get(0).status()).isEqualTo(CompatibilityStatus.PASS);
        assertThat(report.checks().get(0).missingFields()).isEmpty();
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.PASS);
        assertThat(report.hasFailure()).isFalse();
    }

    @Test
    void partialValidate_socketMismatch_shouldFail() {
        CompatibilityReport report = service().validatePartial(Map.of(
                HardwareCategory.CPU, CPU_ID,
                HardwareCategory.MOTHERBOARD, LGA_MOTHERBOARD_ID));

        CompatibilityCheck check = report.checks().get(0);
        assertThat(check.ruleId()).isEqualTo(CompatibilityRule.CPU_SOCKET_MOTHERBOARD.ruleId());
        assertThat(check.status()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(check.hardwareIds()).containsExactlyInAnyOrder(CPU_ID, LGA_MOTHERBOARD_ID);
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(report.hasFailure()).isTrue();
    }

    @Test
    void partialValidate_missingSocketField_shouldBeUnknown() {
        Hardware cpuWithoutSocket = synthetic(
                "cpu-test-no-socket", HardwareCategory.CPU, "{\"tdp_w\":120}");
        Hardware motherboard = catalogRepository.findById(MOTHERBOARD_ID).orElseThrow();
        FixedCatalogRepository catalog = new FixedCatalogRepository(
                List.of(cpuWithoutSocket, motherboard));

        CompatibilityReport report = service(catalog).validatePartial(Map.of(
                HardwareCategory.CPU, cpuWithoutSocket.hardwareId(),
                HardwareCategory.MOTHERBOARD, MOTHERBOARD_ID));

        CompatibilityCheck check = report.checks().get(0);
        assertThat(check.status()).isEqualTo(CompatibilityStatus.UNKNOWN);
        assertThat(check.missingFields()).containsExactly("cpu.socket");
        // 字段缺失不得折算为 PASS。
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.UNKNOWN);
        assertThat(report.hasFailure()).isFalse();
    }

    @Test
    void partialValidate_unrelatedComponents_shouldRunNoRule() {
        CompatibilityReport report = service().validatePartial(Map.of(
                HardwareCategory.CPU, CPU_ID,
                HardwareCategory.MEMORY,
                "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-5600-cl40"));

        // CPU + 内存之间没有规则，不能因为「没规则可跑」就返回 PASS。
        assertThat(report.checks()).isEmpty();
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void partialValidate_endpointShouldReturnPartialResponseWithoutUserToken() {
        PcBuildInternalController controller = new PcBuildInternalController(
                service(),
                new BuildResultFactory(OBJECT_MAPPER, offerRepository, catalogRepository),
                new InternalUserTokenResolver(token -> {
                    throw new JwtException("partial 校验不读取用户令牌");
                }));

        ApiResponse<PartialValidateResponse> response = controller.validatePartial(
                new PartialValidateRequest(Map.of("cpu", CPU_ID, "motherboard", MOTHERBOARD_ID)));

        assertThat(response.code()).isEqualTo(ApiResponse.SUCCESS_CODE);
        assertThat(response.data().overallStatus()).isEqualTo(CompatibilityStatus.PASS);
        assertThat(response.data().checks()).hasSize(1);
        assertThat(response.data().checks().get(0).componentIds())
                .containsExactlyInAnyOrder(CPU_ID, MOTHERBOARD_ID);
        assertThat(response.data().checks().get(0).missingFields()).isEmpty();
    }

    @Test
    void partialValidateRequest_shouldRejectEmptyUnknownOrBlankComponents() {
        assertComponentError(new PartialValidateRequest(null));
        assertComponentError(new PartialValidateRequest(Map.of()));
        assertComponentError(new PartialValidateRequest(Map.of("apu", CPU_ID)));
        assertComponentError(new PartialValidateRequest(Map.of("cpu", "   ")));
    }

    @Test
    void partialValidate_hardwareOfWrongCategory_shouldFailAsIncomplete() {
        BoxedError error = captureError(() -> service().validatePartial(
                Map.of(HardwareCategory.CPU, "gpu-geforce-rtx-5070-ti-16gb-563955")));

        assertThat(error.code()).isEqualTo(40303);
        assertThat(error.message()).contains("属于");
    }

    // 既有 /validate 仍是九条规则：部分校验不能改变它的行为。
    @Test
    void fullValidate_shouldStillReturnNineRules() {
        CompatibilityReport report = service().validate(completeIds());

        assertThat(report.checks()).hasSize(CompatibilityRule.values().length);
        assertThat(report.checks()).extracting(CompatibilityCheck::ruleId)
                .containsExactly("cpu_socket_motherboard", "motherboard_memory_type",
                        "motherboard_case_form_factor", "gpu_case_length", "cooler_cpu_socket",
                        "cooler_case_height", "gpu_psu_power", "storage_motherboard_m2",
                        "memory_module_count");
        assertThat(report.hasFailure()).isFalse();
    }

    // ------------------------------------------------------------------- 工具

    private HardwareCandidateService candidateService(OfferRepository offers) {
        return new HardwareCandidateService(
                catalogService, new BuildSolver(new CompatibilityValidator()), offers);
    }

    private BuildSolveService service() {
        return service(catalogRepository);
    }

    private BuildSolveService service(HardwareCatalogRepository catalog) {
        CompatibilityValidator validator = new CompatibilityValidator();
        BuildResultFactory factory = new BuildResultFactory(OBJECT_MAPPER, offerRepository, catalog);
        BuildSnapshotService snapshots =
                new BuildSnapshotService(new InMemorySnapshotRepository(), factory);
        return new BuildSolveService(
                new BuildSolver(validator),
                validator,
                new HardwareCatalogService(catalog),
                benchmarkRepository,
                offerRepository,
                snapshots);
    }

    private static HardwareCandidate candidateOf(
            List<HardwareCandidate> candidates, String hardwareId) {
        return candidates.stream()
                .filter(candidate -> candidate.hardware().hardwareId().equals(hardwareId))
                .findFirst()
                .orElseThrow();
    }

    private static Offer offer(
            String offerId, String hardwareId, long priceFen, LocalDate validUntil) {
        return new Offer(
                offerId,
                hardwareId,
                HardwareCategory.CPU,
                "JD",
                "seller",
                "shop",
                hardwareId,
                null,
                priceFen,
                "NORMAL",
                null,
                LocalDate.of(2026, 11, 12),
                validUntil,
                Offer.MATCH_OBSERVED,
                "PLATFORM_OBSERVED",
                null);
    }

    private static Hardware synthetic(
            String hardwareId, HardwareCategory category, String specificationsJson) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(
                specificationsJson, HardwareSpecifications.class);
        return new Hardware(
                hardwareId, category, "test", "test", null, null, specifications,
                "PARTIAL", "CURRENT", "ELIGIBLE");
    }

    private static Map<HardwareCategory, String> completeIds() {
        Map<HardwareCategory, String> ids = new EnumMap<>(HardwareCategory.class);
        ids.put(HardwareCategory.CPU, CPU_ID);
        ids.put(HardwareCategory.MOTHERBOARD, MOTHERBOARD_ID);
        ids.put(HardwareCategory.MEMORY,
                "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-5600-cl40");
        ids.put(HardwareCategory.GPU, "gpu-geforce-rtx-5070-ti-16gb-563955");
        ids.put(HardwareCategory.PSU, "psu-segotep-gm750w");
        ids.put(HardwareCategory.CASE, "case-lian-li-lancool-205-mesh");
        ids.put(HardwareCategory.COOLER, "cooler-thermalright-peerless-assassin");
        ids.put(HardwareCategory.STORAGE, "storage-kingston-nv3-1-tb-591379");
        return ids;
    }

    private static void assertComponentError(PartialValidateRequest request) {
        assertThat(captureError(request::toHardwareIds).code()).isEqualTo(40303);
    }

    private static BoxedError captureError(Runnable action) {
        try {
            action.run();
        } catch (BusinessException exception) {
            return new BoxedError(
                    exception.getErrorCode().code(), String.valueOf(exception.getMessage()));
        }
        throw new AssertionError("期望抛出 BusinessException，但没有抛出");
    }

    private record BoxedError(int code, String message) {
    }

    /** 固定报价集合，用于构造「多报价 / 无报价」分支。 */
    private static final class FixedOfferRepository implements OfferRepository {

        private final List<Offer> offers;

        private FixedOfferRepository(List<Offer> offers) {
            this.offers = List.copyOf(offers);
        }

        @Override
        public List<Offer> findAll() {
            return offers;
        }

        @Override
        public List<Offer> findByHardwareId(String hardwareId) {
            return offers.stream()
                    .filter(offer -> offer.hardwareId().equals(hardwareId))
                    .toList();
        }

        @Override
        public String dataStatus() {
            return "TEST";
        }

        @Override
        public String priceUnit() {
            return "CNY_FEN";
        }
    }

    /** 固定目录，用于注入缺字段的合成硬件。 */
    private static final class FixedCatalogRepository implements HardwareCatalogRepository {

        private final List<Hardware> hardware;

        private FixedCatalogRepository(List<Hardware> hardware) {
            this.hardware = List.copyOf(hardware);
        }

        @Override
        public List<Hardware> findAll() {
            return hardware;
        }

        @Override
        public Optional<Hardware> findById(String hardwareId) {
            return hardware.stream()
                    .filter(item -> item.hardwareId().equals(hardwareId))
                    .findFirst();
        }

        @Override
        public String catalogVersion() {
            return "test-catalog";
        }
    }

    /** 快照仓储替身：部分校验不落库，这里只满足组装依赖。 */
    private static final class InMemorySnapshotRepository implements BuildSnapshotRepository {

        @Override
        public void save(BuildSnapshot snapshot) {
            throw new AssertionError("部分校验不得写快照");
        }

        @Override
        public Optional<BuildSnapshot> findByIdAndUserId(UUID buildId, UUID userId) {
            return Optional.empty();
        }
    }
}
