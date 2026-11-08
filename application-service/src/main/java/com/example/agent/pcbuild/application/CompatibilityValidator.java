package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.ExternalPower;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import org.springframework.stereotype.Component;

/**
 * 八条硬件兼容性规则。
 *
 * <p>强制约定：任何参与判断的字段缺失都返回 {@link CompatibilityStatus#UNKNOWN}，
 * 并在 message 中写明缺失项。规则永远不跳过；调用方不得把 {@code UNKNOWN} 展示成 {@code PASS}。
 * 求解器只把 {@code FAIL} 当作硬冲突。</p>
 */
@Component
public class CompatibilityValidator {

    /** 单条规则缺少组件时的统一说明前缀。 */
    private static final String MISSING_COMPONENT = "缺少必要组件";

    /** 电源基础负载：主板、内存、存储、风扇等的整数估算，单位 W。 */
    private static final int BASE_SYSTEM_LOAD_W = 150;

    /** 电源功率冗余：要求额定功率不低于「基础负载 × 1.3」。 */
    private static final int HEADROOM_NUMERATOR = 13;

    private static final int HEADROOM_DENOMINATOR = 10;

    private static final String CONNECTOR_12VHPWR = "PCIE_12VHPWR";

    private static final String CONNECTOR_8PIN = "PCIE_8PIN";

    private static final String INTERFACE_M2 = "M.2";

    private static final String INTERFACE_SATA = "SATA";

    /**
     * 校验全部八条规则，顺序固定。
     *
     * @param selection 硬件组合；允许部分为空，空项对应规则返回 {@code UNKNOWN}
     * @return 兼容性报告
     */
    public CompatibilityReport validate(HardwareSelection selection) {
        List<CompatibilityCheck> checks = new ArrayList<>();
        for (CompatibilityRule rule : CompatibilityRule.values()) {
            checks.add(check(rule, selection));
        }
        return new CompatibilityReport(
                CompatibilityReport.RULE_VERSION,
                CompatibilityReport.aggregate(checks),
                checks);
    }

    /**
     * 校验单条规则，供求解器在增量剪枝时复用同一套判断。
     *
     * @param rule      规则
     * @param selection 当前组合
     * @return 规则结论
     */
    public CompatibilityCheck check(CompatibilityRule rule, HardwareSelection selection) {
        return switch (rule) {
            case CPU_SOCKET_MOTHERBOARD -> checkCpuSocket(selection);
            case MOTHERBOARD_MEMORY_TYPE -> checkMemoryType(selection);
            case MOTHERBOARD_CASE_FORM_FACTOR -> checkFormFactor(selection);
            case GPU_CASE_LENGTH -> checkGpuLength(selection);
            case COOLER_CPU_SOCKET -> checkCoolerSocket(selection);
            case COOLER_CASE_HEIGHT -> checkCoolerHeight(selection);
            case GPU_PSU_POWER -> checkGpuPower(selection);
            case STORAGE_MOTHERBOARD_M2 -> checkStorageInterface(selection);
        };
    }

    private CompatibilityCheck checkCpuSocket(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.CPU_SOCKET_MOTHERBOARD;
        Hardware cpu = selection.cpu();
        Hardware motherboard = selection.motherboard();
        if (cpu == null || motherboard == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：CPU 或主板");
        }
        String cpuSocket = cpu.specifications().socket();
        String boardSocket = motherboard.specifications().socket();
        if (isBlank(cpuSocket) || isBlank(boardSocket)) {
            return result(rule, CompatibilityStatus.UNKNOWN, "CPU 或主板缺少 socket 字段", cpu, motherboard);
        }
        if (equalsIgnoreCase(cpuSocket, boardSocket)) {
            return result(rule, CompatibilityStatus.PASS,
                    "CPU 插槽 " + cpuSocket + " 与主板插槽一致", cpu, motherboard);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "CPU 插槽 " + cpuSocket + " 与主板插槽 " + boardSocket + " 不一致", cpu, motherboard);
    }

    private CompatibilityCheck checkMemoryType(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.MOTHERBOARD_MEMORY_TYPE;
        Hardware motherboard = selection.motherboard();
        Hardware memory = selection.memory();
        if (motherboard == null || memory == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：主板或内存");
        }
        String boardType = motherboard.specifications().memoryType();
        String memoryType = memory.specifications().memoryType();
        if (isBlank(boardType) || isBlank(memoryType)) {
            return result(rule, CompatibilityStatus.UNKNOWN, "主板或内存缺少内存类型字段",
                    motherboard, memory);
        }
        if (equalsIgnoreCase(boardType, memoryType)) {
            return result(rule, CompatibilityStatus.PASS,
                    "主板与内存均为 " + boardType, motherboard, memory);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "主板支持 " + boardType + "，内存为 " + memoryType, motherboard, memory);
    }

    private CompatibilityCheck checkFormFactor(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.MOTHERBOARD_CASE_FORM_FACTOR;
        Hardware motherboard = selection.motherboard();
        Hardware pcCase = selection.pcCase();
        if (motherboard == null || pcCase == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：主板或机箱");
        }
        String boardFormFactor = motherboard.specifications().formFactor();
        List<String> supported = pcCase.specifications().supportedMainboardFormFactors();
        if (isBlank(boardFormFactor) || supported == null || supported.isEmpty()) {
            return result(rule, CompatibilityStatus.UNKNOWN, "主板板型或机箱支持板型缺失",
                    motherboard, pcCase);
        }
        boolean isSupported = supported.stream()
                .filter(Objects::nonNull)
                .anyMatch(candidate -> equalsIgnoreCase(candidate.trim(), boardFormFactor.trim()));
        if (isSupported) {
            return result(rule, CompatibilityStatus.PASS,
                    "机箱支持 " + boardFormFactor + " 主板", motherboard, pcCase);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "机箱仅支持 " + String.join("/", supported) + "，主板为 " + boardFormFactor,
                motherboard, pcCase);
    }

    private CompatibilityCheck checkGpuLength(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.GPU_CASE_LENGTH;
        Hardware gpu = selection.gpu();
        Hardware pcCase = selection.pcCase();
        if (gpu == null || pcCase == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：显卡或机箱");
        }
        Integer gpuLength = gpu.specifications().lengthMm();
        Integer maxLength = pcCase.specifications().maxGpuLengthMm();
        if (gpuLength == null || maxLength == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, "显卡长度或机箱限长缺失", gpu, pcCase);
        }
        if (gpuLength <= maxLength) {
            return result(rule, CompatibilityStatus.PASS,
                    "显卡 " + gpuLength + "mm 未超过机箱限长 " + maxLength + "mm", gpu, pcCase);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "显卡 " + gpuLength + "mm 超过机箱限长 " + maxLength + "mm", gpu, pcCase);
    }

    private CompatibilityCheck checkCoolerSocket(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.COOLER_CPU_SOCKET;
        Hardware cooler = selection.cooler();
        Hardware cpu = selection.cpu();
        if (cooler == null || cpu == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：散热器或 CPU");
        }
        String cpuSocket = cpu.specifications().socket();
        List<String> supportedSockets = cooler.specifications().supportedSockets();
        if (isBlank(cpuSocket) || supportedSockets == null || supportedSockets.isEmpty()) {
            return result(rule, CompatibilityStatus.UNKNOWN, "CPU 插槽或散热器支持列表缺失",
                    cooler, cpu);
        }
        boolean isSupported = supportedSockets.stream()
                .filter(Objects::nonNull)
                .anyMatch(socket -> equalsIgnoreCase(socket.trim(), cpuSocket.trim()));
        if (isSupported) {
            return result(rule, CompatibilityStatus.PASS,
                    "散热器支持 " + cpuSocket, cooler, cpu);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "散热器不支持 " + cpuSocket + "，仅支持 " + String.join("/", supportedSockets),
                cooler, cpu);
    }

    private CompatibilityCheck checkCoolerHeight(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.COOLER_CASE_HEIGHT;
        Hardware cooler = selection.cooler();
        Hardware pcCase = selection.pcCase();
        if (cooler == null || pcCase == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：散热器或机箱");
        }
        Integer coolerHeight = cooler.specifications().heightMm();
        Integer maxHeight = pcCase.specifications().maxCoolerHeightMm();
        // 机箱未提供限高（fixture 中为 null）时必须 UNKNOWN，禁止当作 PASS。
        if (coolerHeight == null || maxHeight == null) {
            return result(rule, CompatibilityStatus.UNKNOWN,
                    "散热器高度或机箱最大散热高度缺失（机箱未提供限高时无法确认）", cooler, pcCase);
        }
        if (coolerHeight <= maxHeight) {
            return result(rule, CompatibilityStatus.PASS,
                    "散热器 " + coolerHeight + "mm 未超过机箱限高 " + maxHeight + "mm", cooler, pcCase);
        }
        return result(rule, CompatibilityStatus.FAIL,
                "散热器 " + coolerHeight + "mm 超过机箱限高 " + maxHeight + "mm", cooler, pcCase);
    }

    private CompatibilityCheck checkGpuPower(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.GPU_PSU_POWER;
        Hardware cpu = selection.cpu();
        Hardware gpu = selection.gpu();
        Hardware psu = selection.psu();
        if (cpu == null || gpu == null || psu == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：CPU、显卡或电源");
        }
        Integer cpuTdp = cpu.specifications().tdpW();
        Integer gpuTdp = gpu.specifications().tdpW();
        Integer wattage = psu.specifications().wattageW();
        ExternalPower externalPower = gpu.specifications().externalPower();
        if (cpuTdp == null || gpuTdp == null || wattage == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, "CPU TDP、显卡 TDP 或电源功率缺失",
                    cpu, gpu, psu);
        }
        if (externalPower == null || isBlank(externalPower.connectorType())
                || externalPower.count() == null || externalPower.count() <= 0) {
            return result(rule, CompatibilityStatus.UNKNOWN, "显卡外接供电接口信息缺失", cpu, gpu, psu);
        }
        Integer provided = availableConnectorCount(psu.specifications(), externalPower.connectorType());
        if (provided == null) {
            return result(rule, CompatibilityStatus.UNKNOWN,
                    "电源未提供 " + externalPower.connectorType() + " 接口数量", cpu, gpu, psu);
        }
        if (provided < externalPower.count()) {
            return result(rule, CompatibilityStatus.FAIL,
                    "显卡需要 " + externalPower.count() + " 个 " + externalPower.connectorType()
                            + " 接口，电源仅提供 " + provided + " 个", cpu, gpu, psu);
        }
        long baseLoad = (long) BASE_SYSTEM_LOAD_W + cpuTdp + gpuTdp;
        long requiredWattage = baseLoad * HEADROOM_NUMERATOR / HEADROOM_DENOMINATOR;
        if (wattage < baseLoad) {
            return result(rule, CompatibilityStatus.FAIL,
                    "电源 " + wattage + "W 低于整机基础负载 " + baseLoad + "W", cpu, gpu, psu);
        }
        if (wattage < requiredWattage) {
            return result(rule, CompatibilityStatus.WARNING,
                    "电源 " + wattage + "W 可用但无 30% 冗余，建议不低于 " + requiredWattage + "W",
                    cpu, gpu, psu);
        }
        return result(rule, CompatibilityStatus.PASS,
                "电源 " + wattage + "W 满足基础负载 " + baseLoad + "W 与供电接口需求",
                cpu, gpu, psu);
    }

    private CompatibilityCheck checkStorageInterface(HardwareSelection selection) {
        CompatibilityRule rule = CompatibilityRule.STORAGE_MOTHERBOARD_M2;
        Hardware motherboard = selection.motherboard();
        Hardware storage = selection.storage();
        if (motherboard == null || storage == null) {
            return result(rule, CompatibilityStatus.UNKNOWN, MISSING_COMPONENT + "：主板或存储");
        }
        String interfaceType = storage.specifications().interfaceType();
        String formFactor = storage.specifications().formFactor();
        if (isBlank(interfaceType)) {
            return result(rule, CompatibilityStatus.UNKNOWN, "存储接口类型缺失", motherboard, storage);
        }
        String normalized = interfaceType.toUpperCase(Locale.ROOT);
        boolean isM2 = normalized.contains(INTERFACE_M2)
                || (formFactor != null && formFactor.toUpperCase(Locale.ROOT).startsWith(INTERFACE_M2));
        if (isM2) {
            Integer m2Slots = motherboard.specifications().m2SlotCount();
            if (m2Slots == null) {
                return result(rule, CompatibilityStatus.UNKNOWN, "主板缺少 M.2 插槽数量", motherboard, storage);
            }
            if (m2Slots >= 1) {
                return result(rule, CompatibilityStatus.PASS,
                        "主板提供 " + m2Slots + " 个 M.2 插槽", motherboard, storage);
            }
            return result(rule, CompatibilityStatus.FAIL, "主板没有 M.2 插槽", motherboard, storage);
        }
        if (normalized.contains(INTERFACE_SATA)) {
            Integer sataPorts = motherboard.specifications().sataPorts();
            if (sataPorts == null) {
                return result(rule, CompatibilityStatus.UNKNOWN, "主板缺少 SATA 接口数量", motherboard, storage);
            }
            if (sataPorts >= 1) {
                return result(rule, CompatibilityStatus.PASS,
                        "主板提供 " + sataPorts + " 个 SATA 接口", motherboard, storage);
            }
            return result(rule, CompatibilityStatus.FAIL, "主板没有 SATA 接口", motherboard, storage);
        }
        return result(rule, CompatibilityStatus.UNKNOWN,
                "无法识别的存储接口类型: " + interfaceType, motherboard, storage);
    }

    private Integer availableConnectorCount(HardwareSpecifications psu, String connectorType) {
        if (CONNECTOR_12VHPWR.equalsIgnoreCase(connectorType)) {
            return psu.pcie12vhpwrCount();
        }
        if (CONNECTOR_8PIN.equalsIgnoreCase(connectorType)) {
            return psu.pcie8pinCount();
        }
        return null;
    }

    private CompatibilityCheck result(
            CompatibilityRule rule,
            CompatibilityStatus status,
            String message,
            Hardware... hardware) {
        List<String> hardwareIds = new ArrayList<>();
        for (Hardware item : hardware) {
            if (item != null) {
                hardwareIds.add(item.hardwareId());
            }
        }
        return new CompatibilityCheck(rule.ruleId(), rule.displayName(), status, message, hardwareIds);
    }

    private static boolean equalsIgnoreCase(String left, String right) {
        return left != null && right != null && left.equalsIgnoreCase(right);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
