package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.RiskLevel;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 八条兼容性规则测试：每条规则至少覆盖通过、失败与参数缺失。
 */
class CompatibilityValidatorTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private final JsonHardwareCatalogRepository catalog =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final CompatibilityValidator validator = new CompatibilityValidator();

    @Test
    void baseline_shouldPassAllRulesExceptUnknownCoolerHeight() {
        CompatibilityReport report = validator.validate(baseline());

        assertThat(report.ruleVersion()).isEqualTo("pc-compat-2.0.0");
        assertThat(report.checks()).hasSize(9);
        assertThat(report.hasFailure()).isFalse();
        assertThat(status(report, CompatibilityRule.CPU_SOCKET_MOTHERBOARD))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.MOTHERBOARD_MEMORY_TYPE))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.MOTHERBOARD_CASE_FORM_FACTOR))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.GPU_CASE_LENGTH))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.COOLER_CPU_SOCKET))
                .isEqualTo(CompatibilityStatus.PASS);
        // 机箱未提供 max_cooler_height_mm：按产品策略默认通过，不再阻断推荐。
        assertThat(status(report, CompatibilityRule.COOLER_CASE_HEIGHT))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.GPU_PSU_POWER))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.STORAGE_MOTHERBOARD_M2))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.MEMORY_MODULE_COUNT))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.PASS);
    }

    @Test
    void everyRule_shouldBeBlockingRiskLevel() {
        CompatibilityReport report = validator.validate(baseline());

        assertThat(report.checks()).allSatisfy(check ->
                assertThat(check.riskLevel()).isEqualTo(RiskLevel.BLOCKING));
    }

    @Test
    void memoryModuleCountGreaterThanSlots_shouldFail() {
        Hardware sixModules = synthetic(
                "memory-test-six-modules", HardwareCategory.MEMORY,
                "{\"memory_type\":\"DDR5\",\"capacity_gb\":96,\"module_count\":6,\"module_size_gb\":16}");
        HardwareSelection selection = baseline().with(HardwareCategory.MEMORY, sixModules);

        CompatibilityCheck check = validator.check(CompatibilityRule.MEMORY_MODULE_COUNT, selection);

        assertThat(check.status()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(check.message()).contains("6").contains("4");
    }

    @Test
    void missingMemorySlots_shouldBeUnknownForModuleCount() {
        Hardware motherboard = synthetic(
                "mb-test-no-memory-slots", HardwareCategory.MOTHERBOARD,
                "{\"socket\":\"AM5\",\"form_factor\":\"ATX\",\"memory_type\":\"DDR5\",\"m2_slot_count\":1}");
        HardwareSelection selection = baseline().with(HardwareCategory.MOTHERBOARD, motherboard);

        CompatibilityCheck check = validator.check(CompatibilityRule.MEMORY_MODULE_COUNT, selection);

        assertThat(check.status()).isEqualTo(CompatibilityStatus.UNKNOWN);
        assertThat(check.message()).contains("插槽");
    }

    @Test
    void redundantMemoryModuleCount_shouldPass() {
        CompatibilityCheck check = validator.check(CompatibilityRule.MEMORY_MODULE_COUNT, baseline());

        assertThat(check.status()).isEqualTo(CompatibilityStatus.PASS);
    }

    @Test
    void cpuSocketMismatch_shouldFail() {
        HardwareSelection selection = baseline().with(
                HardwareCategory.MOTHERBOARD, hardware("motherboard-asus-tuf-gaming-b860m-plus-wifi"));

        CompatibilityCheck check = validator.check(CompatibilityRule.CPU_SOCKET_MOTHERBOARD, selection);

        assertThat(check.status()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(check.message()).contains("AM5").contains("LGA1851");
    }

    @Test
    void memoryTypeMismatch_shouldFail() {
        Hardware ddr4 = synthetic(
                "memory-test-ddr4", HardwareCategory.MEMORY,
                "{\"memory_type\":\"DDR4\",\"capacity_gb\":32,\"module_count\":2,\"module_size_gb\":16}");
        HardwareSelection selection = baseline().with(HardwareCategory.MEMORY, ddr4);

        assertThat(validator.check(CompatibilityRule.MOTHERBOARD_MEMORY_TYPE, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void caseNotSupportingAtx_shouldFail() {
        Hardware itxOnly = synthetic(
                "case-test-itx", HardwareCategory.CASE,
                "{\"supported_mainboard_form_factors\":[\"Mini ITX\"],\"max_gpu_length_mm\":400}");
        HardwareSelection selection = baseline().with(HardwareCategory.CASE, itxOnly);

        assertThat(validator.check(CompatibilityRule.MOTHERBOARD_CASE_FORM_FACTOR, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void gpuLongerThanCaseLimit_shouldFail() {
        Hardware shortCase = synthetic(
                "case-test-short", HardwareCategory.CASE,
                "{\"supported_mainboard_form_factors\":[\"ATX\"],\"max_gpu_length_mm\":250}");
        HardwareSelection selection = baseline().with(HardwareCategory.CASE, shortCase);

        assertThat(validator.check(CompatibilityRule.GPU_CASE_LENGTH, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void coolerNotSupportingCpuSocket_shouldFail() {
        Hardware lgaOnly = synthetic(
                "cooler-test-lga", HardwareCategory.COOLER,
                "{\"cooler_type\":\"AIR\",\"height_mm\":150,\"supported_sockets\":[\"LGA1700\"]}");
        HardwareSelection selection = baseline().with(HardwareCategory.COOLER, lgaOnly);

        assertThat(validator.check(CompatibilityRule.COOLER_CPU_SOCKET, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void coolerHigherThanCaseLimit_shouldFail() {
        Hardware limitedCase = synthetic(
                "case-test-low", HardwareCategory.CASE,
                "{\"supported_mainboard_form_factors\":[\"ATX\"],\"max_gpu_length_mm\":400,"
                        + "\"max_cooler_height_mm\":120}");
        HardwareSelection selection = baseline().with(HardwareCategory.CASE, limitedCase);

        assertThat(validator.check(CompatibilityRule.COOLER_CASE_HEIGHT, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void missingCoolerHeight_shouldDefaultToPass() {
        // 真实 fixture：机箱限高为 null，按产品策略默认放行。
        assertThat(validator.check(CompatibilityRule.COOLER_CASE_HEIGHT, baseline()).status())
                .isEqualTo(CompatibilityStatus.PASS);
    }

    @Test
    void gpuPowerConnectorsInsufficient_shouldFail() {
        // RX 9070 XT 需要 3 根 PCIE_8PIN；be quiet! SFX 450W 仅提供 2 根 → FAIL
        HardwareSelection selection = baseline()
                .with(HardwareCategory.GPU, hardware("gpu-radeon-rx-9070-xt-16gb"))
                .with(HardwareCategory.PSU, hardware("psu-be-quiet-sfx-power-3-450"));

        CompatibilityCheck check = validator.check(CompatibilityRule.GPU_PSU_POWER, selection);

        assertThat(check.status()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(check.message()).contains("PCIE_8PIN");
    }

    @Test
    void gpuPowerWithoutHeadroom_shouldWarn() {
        // 接口匹配 + 功率 > baseLoad 但 < baseLoad*1.3 → WARNING
        // 用 synthetic CPU/GPU/PSU 把数值调到 "有余量但不足 30%" 区间
        Hardware lowPowerCpu = synthetic(
                "cpu-test-low-tdp", HardwareCategory.CPU,
                "{\"socket\":\"AM5\",\"core_count\":4,\"thread_count\":8,\"tdp_w\":30}");
        Hardware lowPowerGpu = synthetic(
                "gpu-test-low-power", HardwareCategory.GPU,
                "{\"chipset\":\"test\",\"external_power\":{\"connector_type\":\"PCIE_12VHPWR\",\"count\":1},\"tdp_w\":200,\"length_mm\":300,\"vram_gb\":16}");
        Hardware lowPowerPsu = synthetic(
                "psu-test-headroom", HardwareCategory.PSU,
                "{\"form_factor\":\"ATX\",\"wattage_w\":450,\"pcie_12vhpwr_count\":1,\"pcie_8pin_count\":0,\"efficiency\":\"80+ Gold\",\"modular\":\"Full\",\"length_mm\":140,\"sata_connectors\":4}");
        HardwareSelection selection = baseline()
                .with(HardwareCategory.CPU, lowPowerCpu)
                .with(HardwareCategory.GPU, lowPowerGpu)
                .with(HardwareCategory.PSU, lowPowerPsu);

        // baseLoad = 200(BASE) + 30 + 200 = 430, requiredW = 430*1.3 = 559
        // PSU 450W ∈ [430, 559) → WARNING
        assertThat(validator.check(CompatibilityRule.GPU_PSU_POWER, selection).status())
                .isEqualTo(CompatibilityStatus.WARNING);
    }

    @Test
    void missingExternalPower_shouldBeUnknown() {
        Hardware gpu = synthetic(
                "gpu-test-no-power", HardwareCategory.GPU,
                "{\"chipset\":\"test\",\"tdp_w\":200,\"length_mm\":200}");
        HardwareSelection selection = baseline().with(HardwareCategory.GPU, gpu);

        assertThat(validator.check(CompatibilityRule.GPU_PSU_POWER, selection).status())
                .isEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void missingM2SlotCount_shouldBeUnknown() {
        Hardware motherboard = synthetic(
                "mb-test-no-m2", HardwareCategory.MOTHERBOARD,
                "{\"socket\":\"AM5\",\"form_factor\":\"ATX\",\"memory_type\":\"DDR5\",\"sata_ports\":4}");
        HardwareSelection selection = baseline().with(HardwareCategory.MOTHERBOARD, motherboard);

        assertThat(validator.check(CompatibilityRule.STORAGE_MOTHERBOARD_M2, selection).status())
                .isEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void noM2Slots_shouldFail() {
        Hardware motherboard = synthetic(
                "mb-test-zero-m2", HardwareCategory.MOTHERBOARD,
                "{\"socket\":\"AM5\",\"form_factor\":\"ATX\",\"memory_type\":\"DDR5\",\"m2_slot_count\":0}");
        HardwareSelection selection = baseline().with(HardwareCategory.MOTHERBOARD, motherboard);

        assertThat(validator.check(CompatibilityRule.STORAGE_MOTHERBOARD_M2, selection).status())
                .isEqualTo(CompatibilityStatus.FAIL);
    }

    @Test
    void emptySelection_shouldReturnUnknownForEveryRule() {
        CompatibilityReport report = validator.validate(HardwareSelection.empty());

        assertThat(report.checks()).hasSize(9);
        assertThat(report.checks()).allSatisfy(check ->
                assertThat(check.status()).isEqualTo(CompatibilityStatus.UNKNOWN));
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void checksShouldFollowDeclaredRuleOrder() {
        List<String> ruleIds = validator.validate(baseline()).checks().stream()
                .map(CompatibilityCheck::ruleId)
                .toList();

        assertThat(ruleIds).containsExactly(
                CompatibilityRule.CPU_SOCKET_MOTHERBOARD.ruleId(),
                CompatibilityRule.MOTHERBOARD_MEMORY_TYPE.ruleId(),
                CompatibilityRule.MOTHERBOARD_CASE_FORM_FACTOR.ruleId(),
                CompatibilityRule.GPU_CASE_LENGTH.ruleId(),
                CompatibilityRule.COOLER_CPU_SOCKET.ruleId(),
                CompatibilityRule.COOLER_CASE_HEIGHT.ruleId(),
                CompatibilityRule.GPU_PSU_POWER.ruleId(),
                CompatibilityRule.STORAGE_MOTHERBOARD_M2.ruleId(),
                CompatibilityRule.MEMORY_MODULE_COUNT.ruleId());
    }

    private CompatibilityStatus status(CompatibilityReport report, CompatibilityRule rule) {
        return report.checks().stream()
                .filter(check -> check.ruleId().equals(rule.ruleId()))
                .findFirst()
                .orElseThrow()
                .status();
    }

    private HardwareSelection baseline() {
        // 每类选新 catalog 里真实存在、规格覆盖各校验规则的条目。
        // 注意 PSU 必须带 pcie_12vhpwr_count >= 1，RTX 5070 Ti 需要一个 12VHPWR 接口。
        return HardwareSelection.empty()
                .with(HardwareCategory.CPU, hardware("cpu-amd-ryzen-7-9800x3d"))
                .with(HardwareCategory.MOTHERBOARD, hardware("motherboard-msi-mag-b850m-mortar-wifi"))
                .with(HardwareCategory.MEMORY, hardware(
                        "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-5600-cl40"))
                .with(HardwareCategory.GPU, hardware("gpu-geforce-rtx-5070-ti-16gb-563955"))
                .with(HardwareCategory.PSU, hardware("psu-segotep-gm750w"))
                .with(HardwareCategory.CASE, hardware("case-lian-li-lancool-205-mesh"))
                .with(HardwareCategory.COOLER, hardware("cooler-thermalright-peerless-assassin"))
                .with(HardwareCategory.STORAGE, hardware("storage-kingston-nv3-1-tb-591379"));
    }

    private Hardware hardware(String hardwareId) {
        return catalog.findById(hardwareId).orElseThrow();
    }

    private Hardware synthetic(String hardwareId, HardwareCategory category, String specificationsJson) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(
                specificationsJson, HardwareSpecifications.class);
        return new Hardware(
                hardwareId, category, "test", "test", null, null, specifications,
                "PARTIAL", "CURRENT", "ELIGIBLE");
    }
}
