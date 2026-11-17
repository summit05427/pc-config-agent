package com.example.agent.pcbuild;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.empty;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * PC 配置内部接口集成测试：完整安全过滤器链 + 真实 PostgreSQL。
 */
@SpringBootTest(properties = {
        "spring.flyway.enabled=true",
        "app.model.runtime-enabled=true",
        "app.model.internal-auth.client-id=agent-service",
        "app.model.internal-auth.client-secret=test-only-internal-secret"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Testcontainers
class PcBuildApiTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private static final String CANDIDATES_PATH = "/internal/v1/pc/hardware/candidates";

    private static final String HARDWARE_PATH = "/internal/v1/pc/hardware";

    private static final String BENCHMARKS_PATH = "/internal/v1/pc/benchmarks";

    private static final String OFFERS_PATH = "/internal/v1/pc/offers";

    private static final String COMPOSE_PATH = "/internal/v1/pc/builds/compose";

    private static final String VALIDATE_PATH = "/internal/v1/pc/builds/validate";

    private static final String VALIDATE_PARTIAL_PATH = "/internal/v1/pc/builds/validate-partial";

    private static final String BUILDS_PATH = "/internal/v1/pc/builds";

    private static final String USER_TOKEN_HEADER = "X-User-Token";

    private static final String SERVICE_TOKEN_PATH = "/internal/v1/auth/service-token";

    private static final String LOGIN_PATH = "/api/v1/auth/login";

    private static final String CLIENT_ID = "agent-service";

    private static final String CLIENT_SECRET = "test-only-internal-secret";

    private static final String ADMIN_PASSWORD = "test-only-password";

    private static final String DEMO_PASSWORD = "test-only-demo-password";

    // 每类选一个新 catalog 里真实存在、规格完备的条目做基线。
    // PSU 必须带 pcie_12vhpwr_count >= 1，RTX 5070 Ti 需要一根 12VHPWR 接口。
    private static final String BASELINE_VALIDATE_BODY = """
            {
              "cpu": "cpu-amd-ryzen-7-9800x3d",
              "motherboard": "motherboard-msi-mag-b850m-mortar-wifi",
              "memory": "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-5600-cl40",
              "gpu": "gpu-geforce-rtx-5070-ti-16gb-563955",
              "psu": "psu-segotep-gm750w",
              "case": "case-lian-li-lancool-205-mesh",
              "cooler": "cooler-thermalright-peerless-assassin",
              "storage": "storage-kingston-nv3-1-tb-591379"
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JsonHardwareCatalogRepository catalogRepository;

    @Autowired
    private JsonOfferRepository offerRepository;

    @Test
    void candidates_shouldRequireServiceTokenAndSupportCategoryFilter() throws Exception {
        mockMvc.perform(get(CANDIDATES_PATH))
                .andExpect(status().isUnauthorized());

        long catalogTotal = catalogRepository.findAll().size();
        long gpuTotal = catalogRepository.findAll().stream()
                .filter(item -> item.category() == HardwareCategory.GPU)
                .count();

        String bearer = bearerToken();
        mockMvc.perform(get(CANDIDATES_PATH).header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.total").value(catalogTotal))
                .andExpect(jsonPath("$.data.catalogVersion").isNotEmpty());

        mockMvc.perform(get(CANDIDATES_PATH)
                        .param("category", "GPU")
                        .header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(gpuTotal))
                .andExpect(jsonPath("$.data.list[*].category", not(empty())))
                // 决策字段：最低可用报价与兼容性关键字段缺失项
                .andExpect(jsonPath("$.data.list[0].priceFen").isNumber())
                .andExpect(jsonPath("$.data.list[0].missingFields").isArray());

        mockMvc.perform(get(CANDIDATES_PATH)
                        .param("category", "UNKNOWN")
                        .header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isBadRequest());
    }

    @Test
    void hardwareDetail_shouldReturnBrandAnd404ForUnknown() throws Exception {
        String bearer = bearerToken();
        mockMvc.perform(get(HARDWARE_PATH + "/gpu-geforce-rtx-5070-ti-16gb-563955")
                        .header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.hardwareId").value("gpu-geforce-rtx-5070-ti-16gb-563955"))
                .andExpect(jsonPath("$.data.specSummary").isNotEmpty());

        mockMvc.perform(get(HARDWARE_PATH + "/not-exists")
                        .header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40301));
    }

    @Test
    void benchmarksAndOffers_shouldExposeSourceAndUnits() throws Exception {
        String bearer = bearerToken();
        long offerTotal = offerRepository.findAll().size();
        long verifiedTotal = offerRepository.findAll().stream().filter(Offer::isVerifiedPrice).count();

        mockMvc.perform(get(BENCHMARKS_PATH).header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                // 跑分条数随 PassMark 匹配结果变化，这里只校验字段存在与类型。
                .andExpect(jsonPath("$.data.total").isNumber());

        mockMvc.perform(get(OFFERS_PATH).header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.dataStatus").value("PLATFORM_OBSERVED_ONLY"))
                .andExpect(jsonPath("$.data.priceUnit").value("CNY_FEN"))
                .andExpect(jsonPath("$.data.verifiedOfferCount").value(verifiedTotal))
                // 全部 PLATFORM_OBSERVED，非核验计数即 offers 总数。
                .andExpect(jsonPath("$.data.mockOfferCount").value(offerTotal - verifiedTotal))
                .andExpect(jsonPath("$.data.total").value(offerTotal));

        mockMvc.perform(get(OFFERS_PATH)
                        .param("hardwareId", "cpu-amd-ryzen-7-9800x3d")
                        .header(HttpHeaders.AUTHORIZATION, bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.list[0].priceFen").value(379900))
                .andExpect(jsonPath("$.data.list[0].priceSource").value("PLATFORM_OBSERVED"))
                .andExpect(jsonPath("$.data.list[0].verifiedPrice").value(false));
    }

    @Test
    void validate_shouldReturnAllNineRulesAndDefaultCoolerHeightToPass() throws Exception {
        mockMvc.perform(post(VALIDATE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(BASELINE_VALIDATE_BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.valid").value(true))
                .andExpect(jsonPath("$.data.report.ruleVersion").value("pc-compat-2.0.0"))
                .andExpect(jsonPath("$.data.report.hasFailure").value(false))
                // 机箱未提供限高：按产品策略默认通过，整体报告为 PASS
                .andExpect(jsonPath("$.data.report.overallStatus").value("PASS"))
                .andExpect(jsonPath("$.data.report.checks.length()").value(9))
                .andExpect(jsonPath("$.data.report.checks[5].ruleId").value("cooler_case_height"))
                .andExpect(jsonPath("$.data.report.checks[5].status").value("PASS"))
                .andExpect(jsonPath("$.data.report.checks[5].riskLevel").value("BLOCKING"))
                .andExpect(jsonPath("$.data.report.checks[8].ruleId").value("memory_module_count"))
                .andExpect(jsonPath("$.data.report.checks[8].status").value("PASS"));
    }

    @Test
    void validate_shouldRejectIncompleteSelection() throws Exception {
        mockMvc.perform(post(VALIDATE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"cpu\":\"cpu-amd-ryzen-7-9800x3d\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validatePartial_shouldRunOnlyRulesCoveredBySelectedComponents() throws Exception {
        // 只选 CPU + 主板：只有 cpu_socket_motherboard 可判定，其余规则不执行；
        // 不携带 X-User-Token，与 /validate 一致。
        mockMvc.perform(post(VALIDATE_PARTIAL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"components": {
                                  "cpu": "cpu-amd-ryzen-7-9800x3d",
                                  "motherboard": "motherboard-msi-mag-b850m-mortar-wifi"
                                }}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.overallStatus").value("PASS"))
                .andExpect(jsonPath("$.data.checks.length()").value(1))
                .andExpect(jsonPath("$.data.checks[0].ruleId").value("cpu_socket_motherboard"))
                .andExpect(jsonPath("$.data.checks[0].status").value("PASS"))
                .andExpect(jsonPath("$.data.checks[0].componentIds.length()").value(2))
                .andExpect(jsonPath("$.data.checks[0].missingFields").isEmpty());
    }

    @Test
    void validatePartial_shouldRejectEmptyUnknownOrBlankComponents() throws Exception {
        String bearer = bearerToken();
        // 完全没有组件
        mockMvc.perform(post(VALIDATE_PARTIAL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"components\":{}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40303));
        // 未知键
        mockMvc.perform(post(VALIDATE_PARTIAL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"components\":{\"apu\":\"cpu-amd-ryzen-7-9800x3d\"}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40303));
        // 空值
        mockMvc.perform(post(VALIDATE_PARTIAL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"components\":{\"cpu\":\"  \"}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40303));
        // components 缺失
        mockMvc.perform(post(VALIDATE_PARTIAL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void compose_shouldPersistSnapshotAndEnforceOwnership() throws Exception {
        String bearer = bearerToken();
        String adminToken = userToken("admin", ADMIN_PASSWORD);
        String demoToken = userToken("demo", DEMO_PASSWORD);

        MvcResult result = mockMvc.perform(post(COMPOSE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .header(USER_TOKEN_HEADER, adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"components\":" + BASELINE_VALIDATE_BODY
                                + ",\"budgetMaxFen\":2000000}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.buildId").isNotEmpty())
                .andExpect(jsonPath("$.data.totalPriceFen").value(
                        org.hamcrest.Matchers.lessThanOrEqualTo(2_000_000)))
                .andExpect(jsonPath("$.data.components.length()").value(8))
                .andExpect(jsonPath("$.data.componentReasons.length()").value(8))
                .andExpect(jsonPath("$.data.componentReasons[0].reason").isNotEmpty())
                .andExpect(jsonPath("$.data.componentReasons[0].priceFen").isNumber())
                .andExpect(jsonPath("$.data.reasonSummary").isNotEmpty())
                .andExpect(jsonPath("$.data.scoringVersion").value("pc-scoring-1.0.0"))
                .andExpect(jsonPath("$.data.requirements.workloadProfile").value("GENERAL"))
                .andExpect(jsonPath("$.data.requirements.renderMode").value("BOTH"))
                .andExpect(jsonPath("$.data.offerDataStatus").value("PLATFORM_OBSERVED_ONLY"))
                .andExpect(jsonPath("$.data.components[*].priceSource", not(empty())))
                .andReturn();
        String buildId = JsonPath.read(result.getResponse().getContentAsString(), "$.data.buildId");

        mockMvc.perform(get(BUILDS_PATH + "/" + buildId)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .header(USER_TOKEN_HEADER, adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.buildId").value(buildId))
                .andExpect(jsonPath("$.data.components.length()").value(8))
                .andExpect(jsonPath("$.data.componentReasons.length()").value(8))
                .andExpect(jsonPath("$.data.reasonSummary").isNotEmpty());

        // 另一个用户读取同一快照必须按不存在处理，不泄露存在性
        mockMvc.perform(get(BUILDS_PATH + "/" + buildId)
                        .header(HttpHeaders.AUTHORIZATION, bearer)
                        .header(USER_TOKEN_HEADER, demoToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40302));
    }

    private String bearerToken() throws Exception {
        MvcResult result = mockMvc.perform(post(SERVICE_TOKEN_PATH)
                        .param("client_id", CLIENT_ID)
                        .param("client_secret", CLIENT_SECRET))
                .andExpect(status().isOk())
                .andReturn();
        String token = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + token;
    }

    private String userToken(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        return JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
    }
}
