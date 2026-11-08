package com.example.agent.pcbuild.domain;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * 一套八件硬件的组合。
 *
 * <p>使用显式字段而不是 {@code Map}，避免迭代顺序影响求解结果的确定性；
 * {@link #asMap()} 始终按 {@link HardwareCategory#REQUIRED_CATEGORIES} 顺序返回。</p>
 */
public record HardwareSelection(
        Hardware cpu,
        Hardware motherboard,
        Hardware memory,
        Hardware gpu,
        Hardware psu,
        Hardware pcCase,
        Hardware cooler,
        Hardware storage) {

    /**
     * 按类别读取组件。
     *
     * @param category 类别
     * @return 组件；未选择时为 {@code null}
     */
    public Hardware get(HardwareCategory category) {
        return switch (category) {
            case CPU -> cpu;
            case MOTHERBOARD -> motherboard;
            case MEMORY -> memory;
            case GPU -> gpu;
            case PSU -> psu;
            case CASE -> pcCase;
            case COOLER -> cooler;
            case STORAGE -> storage;
        };
    }

    /**
     * @return 按固定类别顺序排列的组件表
     */
    public Map<HardwareCategory, Hardware> asMap() {
        Map<HardwareCategory, Hardware> components = new LinkedHashMap<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            components.put(category, get(category));
        }
        return components;
    }

    /**
     * @return 八个类别是否全部选择
     */
    public boolean isComplete() {
        return HardwareCategory.REQUIRED_CATEGORIES.stream().allMatch(category -> get(category) != null);
    }

    /**
     * 在已选组合上替换某一类别，返回新组合；求解器用它做不可变回溯。
     *
     * @param category 类别
     * @param hardware 新硬件
     * @return 新组合
     */
    public HardwareSelection with(HardwareCategory category, Hardware hardware) {
        return switch (category) {
            case CPU -> new HardwareSelection(hardware, motherboard, memory, gpu, psu, pcCase, cooler, storage);
            case MOTHERBOARD -> new HardwareSelection(cpu, hardware, memory, gpu, psu, pcCase, cooler, storage);
            case MEMORY -> new HardwareSelection(cpu, motherboard, hardware, gpu, psu, pcCase, cooler, storage);
            case GPU -> new HardwareSelection(cpu, motherboard, memory, hardware, psu, pcCase, cooler, storage);
            case PSU -> new HardwareSelection(cpu, motherboard, memory, gpu, hardware, pcCase, cooler, storage);
            case CASE -> new HardwareSelection(cpu, motherboard, memory, gpu, psu, hardware, cooler, storage);
            case COOLER -> new HardwareSelection(cpu, motherboard, memory, gpu, psu, pcCase, hardware, storage);
            case STORAGE -> new HardwareSelection(cpu, motherboard, memory, gpu, psu, pcCase, cooler, hardware);
        };
    }

    /**
     * 生成稳定排序用的组件标识签名。
     *
     * @return 以 {@code |} 连接的硬件标识
     */
    public String idSignature() {
        StringBuilder builder = new StringBuilder();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            if (!builder.isEmpty()) {
                builder.append('|');
            }
            Hardware hardware = get(category);
            builder.append(hardware == null ? "-" : hardware.hardwareId());
        }
        return builder.toString();
    }

    /**
     * @return 从空组合开始构建
     */
    public static HardwareSelection empty() {
        return new HardwareSelection(null, null, null, null, null, null, null, null);
    }

    /**
     * 用已解析的组件表构造组合，缺失项保持 {@code null}。
     *
     * @param components 组件表
     * @return 组合
     */
    public static HardwareSelection from(Map<HardwareCategory, Hardware> components) {
        Objects.requireNonNull(components, "components");
        return empty()
                .withIfPresent(HardwareCategory.CPU, components.get(HardwareCategory.CPU))
                .withIfPresent(HardwareCategory.MOTHERBOARD, components.get(HardwareCategory.MOTHERBOARD))
                .withIfPresent(HardwareCategory.MEMORY, components.get(HardwareCategory.MEMORY))
                .withIfPresent(HardwareCategory.GPU, components.get(HardwareCategory.GPU))
                .withIfPresent(HardwareCategory.PSU, components.get(HardwareCategory.PSU))
                .withIfPresent(HardwareCategory.CASE, components.get(HardwareCategory.CASE))
                .withIfPresent(HardwareCategory.COOLER, components.get(HardwareCategory.COOLER))
                .withIfPresent(HardwareCategory.STORAGE, components.get(HardwareCategory.STORAGE));
    }

    private HardwareSelection withIfPresent(HardwareCategory category, Hardware hardware) {
        return hardware == null ? this : with(category, hardware);
    }
}
