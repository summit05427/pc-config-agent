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

        assertThat(report.ruleVersion()).isEqualTo(CompatibilityReport.RULE_VERSION);
        assertThat(report.checks()).hasSize(8);
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
        // 机箱未提供 max_cooler_height_mm，必须 UNKNOWN。
        assertThat(status(report, CompatibilityRule.COOLER_CASE_HEIGHT))
                .isEqualTo(CompatibilityStatus.UNKNOWN);
        assertThat(status(report, CompatibilityRule.GPU_PSU_POWER))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(status(report, CompatibilityRule.STORAGE_MOTHERBOARD_M2))
                .isEqualTo(CompatibilityStatus.PASS);
        assertThat(report.overallStatus()).isEqualTo(CompatibilityStatus.UNKNOWN);
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
    void missingCoolerHeight_shouldBeUnknown_notPass() {
        // 真实 fixture：机箱限高为 null。
        assertThat(validator.check(CompatibilityRule.COOLER_CASE_HEIGHT, baseline()).status())
                .isEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void gpuPowerConnectorsInsufficient_shouldFail() {
        HardwareSelection selection = baseline()
                .with(HardwareCategory.GPU, hardware("gpu-radeon-rx-9070-xt-16gb"))
                .with(HardwareCategory.PSU, hardware("psu-msi-mag-a650gls-pcie5"));

        CompatibilityCheck check = validator.check(CompatibilityRule.GPU_PSU_POWER, selection);

        assertThat(check.status()).isEqualTo(CompatibilityStatus.FAIL);
        assertThat(check.message()).contains("PCIE_8PIN");
    }

    @Test
    void gpuPowerWithoutHeadroom_shouldWarn() {
        HardwareSelection selection = baseline()
                .with(HardwareCategory.GPU, hardware("gpu-geforce-rtx-5070-ti-16gb"))
                .with(HardwareCategory.PSU, hardware("psu-msi-mag-a650gls-pcie5"));

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

        assertThat(report.checks()).hasSize(8);
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
                CompatibilityRule.STORAGE_MOTHERBOARD_M2.ruleId());
    }

    private CompatibilityStatus status(CompatibilityReport report, CompatibilityRule rule) {
        return report.checks().stream()
                .filter(check -> check.ruleId().equals(rule.ruleId()))
                .findFirst()
                .orElseThrow()
                .status();
    }

    private HardwareSelection baseline() {
        return HardwareSelection.empty()
                .with(HardwareCategory.CPU, hardware("cpu-amd-ryzen-7-9800x3d"))
                .with(HardwareCategory.MOTHERBOARD, hardware("motherboard-msi-mag-b850-tomahawk-max-wifi"))
                .with(HardwareCategory.MEMORY, hardware(
                        "memory-corsair-vengeance-32-gb-2-x-16-gb-ddr5-6000-cl36"))
                .with(HardwareCategory.GPU, hardware("gpu-geforce-rtx-5070-ti-16gb"))
                .with(HardwareCategory.PSU, hardware("psu-montech-century-ii"))
                .with(HardwareCategory.CASE, hardware("case-lian-li-lancool-216"))
                .with(HardwareCategory.COOLER, hardware("cooler-thermalright-peerless-assassin-120-se"))
                .with(HardwareCategory.STORAGE, hardware("storage-kingston-nv3-1-tb"));
    }

    private Hardware hardware(String hardwareId) {
        return catalog.findById(hardwareId).orElseThrow();
    }

    private Hardware synthetic(String hardwareId, HardwareCategory category, String specificationsJson) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(
                specificationsJson, HardwareSpecifications.class);
        return new Hardware(
                hardwareId, category, "test", "test", null, specifications,
                "PARTIAL", "CURRENT", "ELIGIBLE");
    }
}
