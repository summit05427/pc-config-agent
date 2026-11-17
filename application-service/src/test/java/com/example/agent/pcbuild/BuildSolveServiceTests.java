package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.pcbuild.application.BuildResultFactory;
import com.example.agent.pcbuild.application.BuildSnapshotService;
import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.BuildSolver;
import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.application.HardwareCatalogService;
import com.example.agent.pcbuild.application.InternalUserTokenResolver;
import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.BuildComponent;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import com.example.agent.pcbuild.web.PcBuildInternalController;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.pcbuild.web.dto.ComposeRequest;
import com.example.agent.pcbuild.web.dto.ValidateRequest;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.security.TokenClaims;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 指定组合生成方案测试：取价口径、快照写入、失败分支与用户令牌。
 *
 * <p>使用真实 fixture 仓储与内存快照仓储，不启 Spring 容器，也不依赖数据库。</p>
 */
class BuildSolveServiceTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private static final UUID USER_ID = UUID.randomUUID();

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

    private final JsonHardwareCatalogRepository catalogRepository =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offerRepository = new JsonOfferRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarkRepository =
            new JsonBenchmarkRepository(OBJECT_MAPPER);

    private final HardwareCatalogService catalogService =
            new HardwareCatalogService(catalogRepository);

    private final InMemoryBuildSnapshotRepository snapshotRepository =
            new InMemoryBuildSnapshotRepository();

    private final BuildResultFactory resultFactory =
            new BuildResultFactory(OBJECT_MAPPER, offerRepository, catalogRepository);

    private final BuildSnapshotService snapshotService =
            new BuildSnapshotService(snapshotRepository, resultFactory);

    private final BuildSolveService service = newService(offerRepository);

    @Test
    void composeWithCompleteHardware_shouldPersistSnapshotPricedByOfferRepository() {
        BuildResult result = service.composeAndSnapshot(USER_ID, completeIds(), null, null);

        assertThat(result.buildId()).isNotNull();
        assertThat(result.userId()).isEqualTo(USER_ID);
        assertThat(result.components()).hasSize(8);
        assertThat(result.componentRationales()).hasSize(8);
        assertThat(result.compatibilityReport().hasFailure()).isFalse();
        for (BuildComponent component : result.components()) {
            assertThat(component.offer()).isNotNull();
            assertThat(component.offer().priceFen()).isPositive();
            assertThat(offerRepository.findByHardwareId(component.hardware().hardwareId()))
                    .extracting(Offer::offerId)
                    .contains(component.offer().offerId());
        }
        long offerPriceSum = result.components().stream()
                .mapToLong(component -> component.offer().priceFen())
                .sum();
        assertThat(result.totalPriceFen()).isEqualTo(offerPriceSum);

        BuildResultResponse readBack = service.requireBuild(USER_ID, result.buildId());
        assertThat(readBack.buildId()).isEqualTo(result.buildId());
        assertThat(readBack.components()).hasSize(8);
        assertThat(readBack.totalPriceFen()).isEqualTo(offerPriceSum);
        assertThat(readBack.componentReasons()).hasSize(8);
        assertThat(readBack.reasonSummary()).isNotBlank();
        assertThat(snapshotRepository.savedCount()).isEqualTo(1);
    }

    @Test
    void composeOverBudget_shouldFailWithBudgetExceededWithoutSnapshot() {
        long totalPriceFen = service.composeAndSnapshot(USER_ID, completeIds(), null, null).totalPriceFen();

        assertThatThrownBy(() -> service.composeAndSnapshot(USER_ID, completeIds(), totalPriceFen - 1, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> {
                    assertThat(errorCodeOf(exception)).isEqualTo(40309);
                    assertThat(exception.getMessage()).contains("超过预算上限");
                });
        // 只有用于取价的基线快照，超预算请求本身不得落库。
        assertThat(snapshotRepository.savedCount()).isEqualTo(1);
    }

    @Test
    void composeWithExactBudget_shouldSucceed() {
        long totalPriceFen = service.composeAndSnapshot(USER_ID, completeIds(), null, null).totalPriceFen();

        BuildResult result = service.composeAndSnapshot(USER_ID, completeIds(), totalPriceFen, null);

        assertThat(result.totalPriceFen()).isEqualTo(totalPriceFen);
        assertThat(snapshotRepository.savedCount()).isEqualTo(2);
    }

    @Test
    void composeWithMissingCategory_shouldFailAsIncomplete() {
        Map<HardwareCategory, String> hardwareIds = completeIds();
        hardwareIds.remove(HardwareCategory.COOLER);

        assertThatThrownBy(() -> service.composeAndSnapshot(USER_ID, hardwareIds, null, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(errorCodeOf(exception)).isEqualTo(40303));
        assertThat(snapshotRepository.savedCount()).isZero();
    }

    @Test
    void composeWithWrongCategoryHardware_shouldFailAsIncomplete() {
        Map<HardwareCategory, String> hardwareIds = completeIds();
        hardwareIds.put(HardwareCategory.CPU, COMPLETE_HARDWARE_IDS.get(HardwareCategory.GPU));

        assertThatThrownBy(() -> service.composeAndSnapshot(USER_ID, hardwareIds, null, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> {
                    assertThat(errorCodeOf(exception)).isEqualTo(40303);
                    assertThat(exception.getMessage()).contains("属于");
                });
        assertThat(snapshotRepository.savedCount()).isZero();
    }

    @Test
    void composeWithoutUsableOffer_shouldFailInsteadOfFillingZeroPrice() {
        BuildSolveService serviceWithoutOffers = newService(new EmptyOfferRepository());

        assertThatThrownBy(() -> serviceWithoutOffers.composeAndSnapshot(USER_ID, completeIds(), null, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(errorCodeOf(exception)).isEqualTo(40307));
        assertThat(snapshotRepository.savedCount()).isZero();
    }

    @Test
    void composeWithIncompatibleHardware_shouldReturnStructuredFailureWithoutSnapshot() {
        Map<HardwareCategory, String> hardwareIds = completeIds();
        // AM5 的 CPU 换到 LGA1700 主板：插槽规则必然 FAIL，不能被当成可用方案落库。
        hardwareIds.put(HardwareCategory.MOTHERBOARD, "motherboard-asrock-b760-pro-rs");

        assertThatThrownBy(() -> service.composeAndSnapshot(USER_ID, hardwareIds, null, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> {
                    assertThat(errorCodeOf(exception)).isEqualTo(40308);
                    assertThat(exception.getMessage()).contains("cpu_socket_motherboard");
                });
        assertThat(snapshotRepository.savedCount()).isZero();
    }

    @Test
    void composeWithoutUserToken_shouldFailAuthentication() {
        PcBuildInternalController controller = controller(new InternalUserTokenResolver(rejectingDecoder()));
        ComposeRequest request = new ComposeRequest(validateRequest(), null, null);

        assertThatThrownBy(() -> controller.compose(request, null))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(errorCodeOf(exception)).isEqualTo(40306));
        assertThatThrownBy(() -> controller.compose(request, "   "))
                .isInstanceOf(BusinessException.class)
                .satisfies(exception -> assertThat(errorCodeOf(exception)).isEqualTo(40306));
        assertThat(snapshotRepository.savedCount()).isZero();
    }

    @Test
    void composeEndpoint_shouldReturnBuildOwnedByTokenSubject() {
        UUID tokenSubject = UUID.randomUUID();
        Jwt userToken = Jwt.withTokenValue("test-user-token")
                .header("alg", "RS256")
                .claim(TokenClaims.TOKEN_USE_CLAIM, TokenClaims.TOKEN_USE_ACCESS)
                .subject(tokenSubject.toString())
                .build();
        PcBuildInternalController controller = controller(
                new InternalUserTokenResolver(token -> userToken));

        ApiResponse<BuildResultResponse> response =
                controller.compose(new ComposeRequest(validateRequest(), null, null), "test-user-token");

        assertThat(response.code()).isEqualTo(ApiResponse.SUCCESS_CODE);
        assertThat(response.data().buildId()).isNotNull();
        assertThat(response.data().components()).hasSize(8);
        // 快照归属与令牌 sub 一致，不能落到别的用户名下。
        assertThat(service.requireBuild(tokenSubject, response.data().buildId()).buildId())
                .isEqualTo(response.data().buildId());
    }

    private BuildSolveService newService(OfferRepository offers) {
        return new BuildSolveService(
                new BuildSolver(new CompatibilityValidator()),
                new CompatibilityValidator(),
                catalogService,
                benchmarkRepository,
                offers,
                snapshotService);
    }

    private PcBuildInternalController controller(InternalUserTokenResolver tokenResolver) {
        return new PcBuildInternalController(service, resultFactory, tokenResolver);
    }

    private static JwtDecoder rejectingDecoder() {
        return token -> {
            throw new JwtException("invalid token");
        };
    }

    private static Map<HardwareCategory, String> completeIds() {
        return new EnumMap<>(COMPLETE_HARDWARE_IDS);
    }

    private static ValidateRequest validateRequest() {
        return new ValidateRequest(
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.CPU),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.MOTHERBOARD),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.MEMORY),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.GPU),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.PSU),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.CASE),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.COOLER),
                COMPLETE_HARDWARE_IDS.get(HardwareCategory.STORAGE));
    }

    private static int errorCodeOf(Throwable exception) {
        return ((BusinessException) exception).getErrorCode().code();
    }

    /** 内存快照仓储：只插入、按归属读取，模拟 append-only 语义。 */
    private static final class InMemoryBuildSnapshotRepository implements BuildSnapshotRepository {

        private final Map<UUID, BuildSnapshot> rows = new HashMap<>();

        @Override
        public void save(BuildSnapshot snapshot) {
            if (rows.putIfAbsent(snapshot.buildId(), snapshot) != null) {
                throw new IllegalStateException("快照已存在，append-only 表不允许覆盖: " + snapshot.buildId());
            }
        }

        @Override
        public Optional<BuildSnapshot> findByIdAndUserId(UUID buildId, UUID userId) {
            return Optional.ofNullable(rows.get(buildId))
                    .filter(snapshot -> snapshot.userId().equals(userId));
        }

        private int savedCount() {
            return rows.size();
        }
    }

    /** 没有任何报价的仓储，用于验证「无可用报价」时不补 0 价。 */
    private static final class EmptyOfferRepository implements OfferRepository {

        @Override
        public List<Offer> findAll() {
            return List.of();
        }

        @Override
        public List<Offer> findByHardwareId(String hardwareId) {
            return List.of();
        }

        @Override
        public String dataStatus() {
            return "NO_OFFERS";
        }

        @Override
        public String priceUnit() {
            return "CNY_FEN";
        }
    }
}
