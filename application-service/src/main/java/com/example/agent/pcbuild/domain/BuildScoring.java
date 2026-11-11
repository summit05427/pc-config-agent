package com.example.agent.pcbuild.domain;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 方案评分的单一实现。
 *
 * <p>求解器选优与结果解释共用同一套整数公式，避免「算分」与「讲理由」出现两套口径。
 * 全程使用 {@code long}，不引入浮点；各类别贡献之和严格等于方案总分。</p>
 */
public final class BuildScoring {

    /** 每 GB 内存的评分加成。 */
    public static final long MEMORY_BONUS_PER_GB = 500L;

    /** 每 GB 存储的评分加成。 */
    public static final long STORAGE_BONUS_PER_GB = 20L;

    /** 内存加成上限，避免大容量内存无限拉高总分。 */
    public static final int MEMORY_BONUS_CAP_GB = 64;

    /** 存储加成上限。 */
    public static final int STORAGE_BONUS_CAP_GB = 2048;

    /** 显存加成上限，避免超大数据中心卡把分数拉得不可比。 */
    public static final int VRAM_BONUS_CAP_GB = 24;

    /** AI 推理画像每 GB 显存加成，显存是能否装载模型的第一约束。 */
    public static final long VRAM_BONUS_PER_GB_AI = 3000L;

    /** 视频剪辑画像每 GB 显存加成，显存影响时间线预览与编码缓存。 */
    public static final long VRAM_BONUS_PER_GB_VIDEO = 1000L;

    /**
     * PassMark 单线程分与 CPUMARK 分数量级相差约 10 倍，乘 10 仅做量纲对齐，
     * 不引入额外权重语义。
     */
    private static final long SINGLE_THREAD_SCALE = 10L;

    /** 游戏画像 CPU 分中主分与单线程分各占 50 份，总份数 100。 */
    private static final long CPU_SCORE_BLEND_WEIGHT = 50L;

    private static final long CPU_SCORE_BLEND_TOTAL = 100L;

    private BuildScoring() {
    }

    /**
     * 计算方案总分。
     *
     * @param requirements 需求
     * @param selection    八类硬件，可含 {@code null}
     * @param benchmarks   跑分索引，按 {@code hardwareId} 查找
     * @return 整数总分
     */
    public static long totalScore(
            BuildRequirements requirements,
            Map<HardwareCategory, Hardware> selection,
            Map<String, Benchmark> benchmarks) {
        long total = 0L;
        for (long contribution : contributions(requirements, selection, benchmarks).values()) {
            total += contribution;
        }
        return total;
    }

    /**
     * 计算各类别对总分的原始贡献。
     *
     * <p>CPU/GPU 的权重取整误差统一归入 GPU，保证八项之和与 {@link #totalScore} 完全一致。</p>
     *
     * @param requirements 需求
     * @param selection    八类硬件，可含 {@code null}
     * @param benchmarks   跑分索引
     * @return 按 {@link HardwareCategory#REQUIRED_CATEGORIES} 顺序排列的贡献表
     */
    public static Map<HardwareCategory, Long> contributions(
            BuildRequirements requirements,
            Map<HardwareCategory, Hardware> selection,
            Map<String, Benchmark> benchmarks) {

        Hardware cpu = selection.get(HardwareCategory.CPU);
        Hardware gpu = selection.get(HardwareCategory.GPU);
        Hardware memory = selection.get(HardwareCategory.MEMORY);
        Hardware storage = selection.get(HardwareCategory.STORAGE);

        long cpuScore = cpuScore(requirements.workloadProfile(),
                benchmarkScore(benchmarks, cpu), secondaryScore(benchmarks, cpu));
        long gpuScore = benchmarkScore(benchmarks, gpu);
        long weighted = (cpuScore * requirements.scenario().cpuWeight()
                + gpuScore * requirements.scenario().gpuWeight()) / 100L;
        long memoryContribution = Math.min(capacityGb(memory), MEMORY_BONUS_CAP_GB)
                * MEMORY_BONUS_PER_GB;
        long storageContribution = Math.min(capacityGb(storage), STORAGE_BONUS_CAP_GB)
                * STORAGE_BONUS_PER_GB;
        long vramContribution = vramBonus(requirements.workloadProfile(), gpu);
        long total = weighted + memoryContribution + storageContribution + vramContribution;
        long cpuContribution = cpuScore * requirements.scenario().cpuWeight() / 100L;

        Map<HardwareCategory, Long> contributions = new LinkedHashMap<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            contributions.put(category, switch (category) {
                case CPU -> cpuContribution;
                case MEMORY -> memoryContribution;
                case STORAGE -> storageContribution;
                // GPU 吸收 CPU/GPU 两项权重取整的余数，并包含显存加成。
                case GPU -> total - cpuContribution - memoryContribution - storageContribution;
                case MOTHERBOARD, PSU, CASE, COOLER -> 0L;
            });
        }
        return contributions;
    }

    /**
     * 游戏画像是唯一对单线程敏感的画像：主分与单线程分各占一半，
     * 其他画像仍使用 CPUMARK 主分，保持历史评分口径。
     *
     * @param workloadProfile 画像
     * @param cpumark         主分
     * @param singleThread    单线程分
     * @return CPU 评分
     */
    public static long cpuScore(WorkloadProfile workloadProfile, long cpumark, long singleThread) {
        if (workloadProfile == WorkloadProfile.GAMING) {
            return (cpumark * CPU_SCORE_BLEND_WEIGHT
                    + singleThread * SINGLE_THREAD_SCALE * CPU_SCORE_BLEND_WEIGHT)
                    / CPU_SCORE_BLEND_TOTAL;
        }
        return cpumark;
    }

    /**
     * 显存加成只对显存敏感画像生效，按 GB 线性累计并设置上限。
     *
     * @param workloadProfile 画像
     * @param gpu             显卡
     * @return 显存加成
     */
    public static long vramBonus(WorkloadProfile workloadProfile, Hardware gpu) {
        long vramGb = Math.min(vramGb(gpu), VRAM_BONUS_CAP_GB);
        return switch (workloadProfile) {
            case AI_INFERENCE -> vramGb * VRAM_BONUS_PER_GB_AI;
            case VIDEO_EDITING -> vramGb * VRAM_BONUS_PER_GB_VIDEO;
            default -> 0L;
        };
    }

    private static long benchmarkScore(Map<String, Benchmark> benchmarks, Hardware hardware) {
        if (hardware == null) {
            return 0L;
        }
        Benchmark benchmark = benchmarks.get(hardware.hardwareId());
        return benchmark == null ? 0L : Math.max(0L, benchmark.scoreAsLong());
    }

    private static long secondaryScore(Map<String, Benchmark> benchmarks, Hardware hardware) {
        if (hardware == null) {
            return 0L;
        }
        Benchmark benchmark = benchmarks.get(hardware.hardwareId());
        if (benchmark == null || benchmark.secondaryScore() == null) {
            return 0L;
        }
        return Math.max(0L, Math.round(benchmark.secondaryScore()));
    }

    private static long vramGb(Hardware hardware) {
        if (hardware == null || hardware.specifications().vramGb() == null) {
            return 0L;
        }
        return Math.max(0, hardware.specifications().vramGb());
    }

    private static long capacityGb(Hardware hardware) {
        if (hardware == null || hardware.specifications().capacityGb() == null) {
            return 0L;
        }
        return Math.max(0, hardware.specifications().capacityGb());
    }
}
