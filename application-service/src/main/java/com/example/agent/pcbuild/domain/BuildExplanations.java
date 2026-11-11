package com.example.agent.pcbuild.domain;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 确定性结果解释生成器。
 *
 * <p>只使用求解时已有的硬件规格、跑分、报价与需求拼装文本，不调用模型、不补造数据。
 * 同一份输入在任意机器上得到完全相同的理由与百分比。</p>
 */
public final class BuildExplanations {

    private BuildExplanations() {
    }

    /**
     * 单个组件的解释输入。
     *
     * @param category   硬件类别
     * @param hardwareId 硬件标识
     * @param hardware   硬件详情；快照读取时目录已移除则为 {@code null}
     * @param benchmark  跑分，可为 {@code null}
     * @param priceFen   该件价格，单位分
     */
    public record ComponentInput(
            HardwareCategory category,
            String hardwareId,
            Hardware hardware,
            Benchmark benchmark,
            long priceFen) {
    }

    /**
     * 生成逐类硬件理由。
     *
     * @param requirements  需求
     * @param inputs        组件输入，顺序即输出顺序
     * @param totalPriceFen 方案总价，单位分
     * @return 每个组件一条理由；输入为空时返回空列表
     */
    public static List<ComponentRationale> componentRationales(
            BuildRequirements requirements,
            List<ComponentInput> inputs,
            long totalPriceFen) {

        Map<HardwareCategory, Hardware> selection = new EnumMap<>(HardwareCategory.class);
        Map<String, Benchmark> benchmarks = new HashMap<>();
        for (ComponentInput input : inputs) {
            if (input.hardware() != null) {
                selection.put(input.category(), input.hardware());
            }
            if (input.benchmark() != null) {
                benchmarks.put(input.hardwareId(), input.benchmark());
            }
        }
        Map<HardwareCategory, Long> contributions =
                BuildScoring.contributions(requirements, selection, benchmarks);
        long totalScore = contributions.values().stream().mapToLong(Long::longValue).sum();

        List<ComponentRationale> rationales = new ArrayList<>();
        for (ComponentInput input : inputs) {
            long contribution = contributions.getOrDefault(input.category(), 0L);
            rationales.add(new ComponentRationale(
                    input.category(),
                    input.hardwareId(),
                    reasonOf(requirements, input, contribution, totalScore, totalPriceFen),
                    contribution,
                    input.priceFen()));
        }
        return List.copyOf(rationales);
    }

    /**
     * 生成面向用户的推荐摘要。
     *
     * <p>每个画像都有专用句子；不会把渲染、AI 推理或视频剪辑落到通用兜底。
     * 文案只描述评分口径与选优策略，不承诺帧率、渲染耗时或推理速度。</p>
     *
     * @param requirements 需求
     * @return 推荐摘要
     */
    public static String reasonSummary(BuildRequirements requirements) {
        return profileSummary(requirements) + selectionSummary(requirements);
    }

    private static String profileSummary(BuildRequirements requirements) {
        WorkloadProfile profile = requirements.workloadProfile();
        return switch (profile) {
            case GAMING -> "该方案按游戏画像评分：CPU 主分与单线程分各占一半后按 "
                    + requirements.scenario().cpuWeight() + "% 权重计入，显卡权重 "
                    + requirements.scenario().gpuWeight() + "%，候选按单线程与图形分排序。";
            case VIDEO_EDITING -> "该方案按视频剪辑画像评分：CPU/GPU 权重 "
                    + requirements.scenario().cpuWeight() + "/" + requirements.scenario().gpuWeight()
                    + "，显卡候选按图形分降序，存储候选按容量降序，显存每 GB 计入 "
                    + BuildScoring.VRAM_BONUS_PER_GB_VIDEO + " 分加成（上限 "
                    + BuildScoring.VRAM_BONUS_CAP_GB + "GB）。";
            case PROGRAMMING -> "该方案按编程画像评分：CPU 权重 "
                    + requirements.scenario().cpuWeight() + "%，CPU 候选按核心数降序，内存按容量每 GB 计入 "
                    + BuildScoring.MEMORY_BONUS_PER_GB + " 分加成。";
            case AI_INFERENCE -> "该方案按本地 AI 推理画像评分：GPU 权重 "
                    + requirements.scenario().gpuWeight() + "%，显卡候选按显存降序，显存每 GB 计入 "
                    + BuildScoring.VRAM_BONUS_PER_GB_AI + " 分加成（上限 "
                    + BuildScoring.VRAM_BONUS_CAP_GB + "GB）；CPU 权重 "
                    + requirements.scenario().cpuWeight() + "%。";
            case RENDERING -> renderingSummary(requirements);
            case GENERAL -> "该方案按通用画像评分：CPU/GPU 权重 "
                    + requirements.scenario().cpuWeight() + "/" + requirements.scenario().gpuWeight()
                    + "，按性能与价格平衡选择。";
        };
    }

    private static String renderingSummary(BuildRequirements requirements) {
        return switch (requirements.renderMode()) {
            case CPU -> "该方案按 CPU 渲染取向评分：CPU 权重 "
                    + requirements.scenario().cpuWeight() + "%，CPU 候选按 PassMark 主分降序。";
            case GPU -> "该方案按 GPU 渲染取向评分：GPU 权重 "
                    + requirements.scenario().gpuWeight() + "%，显卡候选按图形分降序。";
            case BOTH -> "该方案按未指定渲染介质的渲染画像评分：CPU/GPU 权重 "
                    + requirements.scenario().cpuWeight() + "/" + requirements.scenario().gpuWeight()
                    + "。";
        };
    }

    private static String selectionSummary(BuildRequirements requirements) {
        if (!requirements.hasBudget()) {
            return "无硬预算，选优按性价比优先（总分×1,000,000/价格）。";
        }
        if (requirements.prefersValue()) {
            return "预算内选优按性价比优先（总分×1,000,000/价格），价格非正记 0。";
        }
        return "预算内选优按性能总分优先，同分时价格更低者优先。";
    }

    private static String reasonOf(
            BuildRequirements requirements,
            ComponentInput input,
            long contribution,
            long totalScore,
            long totalPriceFen) {

        StringBuilder reason = new StringBuilder(categoryReason(requirements, input));
        appendSpecFacts(reason, requirements, input);
        reason.append("该件对方案总分贡献 ")
                .append(percent(contribution, totalScore))
                .append("%（贡献分 ")
                .append(contribution)
                .append("），价格 ")
                .append(input.priceFen())
                .append(" 分，占总价 ")
                .append(percent(input.priceFen(), totalPriceFen))
                .append("%。");
        return reason.toString();
    }

    private static String categoryReason(BuildRequirements requirements, ComponentInput input) {
        WorkloadProfile profile = requirements.workloadProfile();
        return switch (input.category()) {
            case CPU -> cpuReason(requirements, profile);
            case GPU -> gpuReason(requirements, profile);
            case MEMORY -> "MEMORY 候选池按价格升序取前 8；容量每 GB 计入 "
                    + BuildScoring.MEMORY_BONUS_PER_GB + " 分加成（上限 "
                    + BuildScoring.MEMORY_BONUS_CAP_GB + "GB）。";
            case STORAGE -> storageReason(profile);
            case MOTHERBOARD -> "MOTHERBOARD 不直接计入性能分，候选池按价格升序取前 8；"
                    + "选择需满足 CPU 插槽与内存类型兼容。";
            case PSU -> "PSU 不直接计入性能分，候选池按价格升序取前 8；选择需满足显卡供电功率规则。";
            case CASE -> "CASE 不直接计入性能分，候选池按价格升序取前 8；"
                    + "选择需满足主板板型、显卡长度与散热器限高。";
            case COOLER -> "COOLER 不直接计入性能分，候选池按价格升序取前 8；"
                    + "选择需满足 CPU 插槽与机箱限高。";
        };
    }

    private static String cpuReason(BuildRequirements requirements, WorkloadProfile profile) {
        String ordering = switch (profile) {
            case GAMING -> "GAMING 画像按单线程混合评分：PassMark 主分与单线程分各占 50 份后按权重计入，"
                    + "候选池按单线程分降序取前 12。";
            case PROGRAMMING -> "PROGRAMMING 画像候选池按核心数降序（多核优先），"
                    + "PassMark 主分作为次级键取前 12。";
            case VIDEO_EDITING -> "VIDEO_EDITING 画像候选池按 PassMark 主分降序取前 12。";
            case AI_INFERENCE -> "AI_INFERENCE 画像候选池按 PassMark 主分降序取前 12。";
            case RENDERING -> "RENDERING 画像候选池按 PassMark 主分降序取前 12。";
            case GENERAL -> "GENERAL 画像候选池按 PassMark 主分降序取前 12。";
        };
        return ordering + "本方案 CPU 权重 " + requirements.scenario().cpuWeight() + "%。";
    }

    private static String gpuReason(BuildRequirements requirements, WorkloadProfile profile) {
        String ordering = switch (profile) {
            case AI_INFERENCE -> "AI_INFERENCE 画像候选池按显存降序取前 12，显存每 GB 计入 "
                    + BuildScoring.VRAM_BONUS_PER_GB_AI + " 分加成（上限 "
                    + BuildScoring.VRAM_BONUS_CAP_GB + "GB）。";
            case VIDEO_EDITING -> "VIDEO_EDITING 画像显卡候选按图形分降序，显存每 GB 计入 "
                    + BuildScoring.VRAM_BONUS_PER_GB_VIDEO + " 分加成（上限 "
                    + BuildScoring.VRAM_BONUS_CAP_GB + "GB）。";
            case GAMING -> "GAMING 画像显卡候选按图形分降序取前 12。";
            case PROGRAMMING -> "PROGRAMMING 画像显卡候选按图形分降序取前 12。";
            case RENDERING -> "RENDERING 画像显卡候选按图形分降序取前 12。";
            case GENERAL -> "GENERAL 画像显卡候选按图形分降序取前 12。";
        };
        return ordering + "本方案 GPU 权重 " + requirements.scenario().gpuWeight() + "%。";
    }

    private static String storageReason(WorkloadProfile profile) {
        String ordering = profile == WorkloadProfile.VIDEO_EDITING
                ? "STORAGE 候选池按容量降序取前 8"
                : "STORAGE 候选池按价格升序取前 8";
        return ordering + "；容量每 GB 计入 " + BuildScoring.STORAGE_BONUS_PER_GB
                + " 分加成（上限 " + BuildScoring.STORAGE_BONUS_CAP_GB + "GB）。";
    }

    private static void appendSpecFacts(
            StringBuilder reason,
            BuildRequirements requirements,
            ComponentInput input) {

        Hardware hardware = input.hardware();
        boolean hasFacts = false;
        if (hardware != null && input.category() == HardwareCategory.CPU) {
            reason.append("该件 ")
                    .append(text(hardware.specifications().coreCount()))
                    .append(" 核 / ")
                    .append(text(hardware.specifications().threadCount()))
                    .append(" 线程");
            hasFacts = true;
        }
        if (hardware != null && input.category() == HardwareCategory.GPU) {
            reason.append("该件显存 ").append(text(hardware.specifications().vramGb())).append("GB");
            hasFacts = true;
        }
        if (hardware != null
                && (input.category() == HardwareCategory.MEMORY
                || input.category() == HardwareCategory.STORAGE)) {
            reason.append("该件容量 ").append(text(hardware.specifications().capacityGb())).append("GB");
            hasFacts = true;
        }

        Benchmark benchmark = input.benchmark();
        if (input.category() == HardwareCategory.CPU || input.category() == HardwareCategory.GPU) {
            if (benchmark == null) {
                reason.append(hasFacts ? "，" : "该件")
                        .append("缺少跑分数据，按 0 分计入");
            } else {
                if (!hasFacts) {
                    reason.append("该件");
                }
                reason.append("，").append(benchmark.benchmarkType()).append(" 主分 ")
                        .append(benchmark.scoreAsLong());
                if (input.category() == HardwareCategory.CPU
                        && requirements.workloadProfile() == WorkloadProfile.GAMING
                        && benchmark.secondaryScore() != null) {
                    reason.append("、单线程分 ").append(Math.round(benchmark.secondaryScore()));
                }
            }
            hasFacts = true;
        }
        if (hasFacts) {
            reason.append("；");
        }
    }

    private static long percent(long part, long total) {
        if (total <= 0L) {
            return 0L;
        }
        return (part * 100L + total / 2L) / total;
    }

    private static String text(Integer value) {
        return value == null ? "未记录" : String.valueOf(value);
    }
}
