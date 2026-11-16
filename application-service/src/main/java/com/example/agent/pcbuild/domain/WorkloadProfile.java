package com.example.agent.pcbuild.domain;

import java.util.Locale;

/**
 * 工作负载画像：决定场景权重、候选排序策略与评分细则。
 *
 * <p>与 {@link BuildScenario} 的分工：画像表达「用户要做什么」，场景表达「CPU/GPU 权重」。
 * 画像到场景的映射由 {@link #scenarioFor(RenderMode)} 统一给出，避免调用方各自拼权重。</p>
 */
public enum WorkloadProfile {

    GENERAL(50, 50, CandidateRanking.BALANCED),
    GAMING(30, 70, CandidateRanking.SINGLE_THREAD_FIRST),
    VIDEO_EDITING(55, 45, CandidateRanking.GPU_SCORE_FIRST),
    PROGRAMMING(80, 20, CandidateRanking.MULTICORE_FIRST),
    RENDERING(55, 45, CandidateRanking.BALANCED),
    MEDIA(70, 30, CandidateRanking.BALANCED),
    AI_INFERENCE(40, 60, CandidateRanking.VRAM_FIRST);

    /** 候选排序策略；所有策略最终都以 {@code hardwareId} 升序兜底保证确定性。 */
    public enum CandidateRanking {
        BALANCED,
        SINGLE_THREAD_FIRST,
        MULTICORE_FIRST,
        GPU_SCORE_FIRST,
        VRAM_FIRST
    }

    private final int cpuWeight;
    private final int gpuWeight;
    private final CandidateRanking candidateRanking;

    WorkloadProfile(int cpuWeight, int gpuWeight, CandidateRanking candidateRanking) {
        this.cpuWeight = cpuWeight;
        this.gpuWeight = gpuWeight;
        this.candidateRanking = candidateRanking;
    }

    public int cpuWeight() {
        return cpuWeight;
    }

    public int gpuWeight() {
        return gpuWeight;
    }

    public CandidateRanking candidateRanking() {
        return candidateRanking;
    }

    /**
     * 解析外部传入的工作负载名称。
     *
     * <p>同时接受旧命名（{@code CREATIVE}/{@code BALANCED}/{@code OFFICE}/{@code WORKSTATION}），
     * 保证历史请求仍可求解；无法识别时返回 {@code null}。</p>
     *
     * @param raw 原始文本，可为 {@code null}
     * @return 命中画像；无法识别时为 {@code null}
     */
    public static WorkloadProfile parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "GENERAL", "BALANCED", "OFFICE" -> GENERAL;
            case "GAMING" -> GAMING;
            case "VIDEO_EDITING", "CREATIVE" -> VIDEO_EDITING;
            case "PROGRAMMING" -> PROGRAMMING;
            case "RENDERING", "WORKSTATION" -> RENDERING;
            case "MEDIA" -> MEDIA;
            case "AI_INFERENCE" -> AI_INFERENCE;
            default -> null;
        };
    }

    /**
     * 按画像与渲染取向给出实际使用的场景权重。
     *
     * <p>渲染类工作负载的 CPU/GPU 权重取决于用户选择的渲染方式：
     * CPU 渲染按编程类偏向多核，GPU 渲染按游戏类偏向显卡，未指定时取折中的创作场景。</p>
     *
     * @param renderMode 渲染取向，可为 {@code null}
     * @return 场景
     */
    public BuildScenario scenarioFor(RenderMode renderMode) {
        if (this == RENDERING) {
            if (renderMode == RenderMode.CPU) {
                return BuildScenario.PROGRAMMING;
            }
            if (renderMode == RenderMode.GPU) {
                return BuildScenario.GAMING;
            }
            return BuildScenario.CREATIVE;
        }
        return switch (this) {
            case GENERAL -> BuildScenario.BALANCED;
            case GAMING -> BuildScenario.GAMING;
            case VIDEO_EDITING -> BuildScenario.CREATIVE;
            case PROGRAMMING -> BuildScenario.PROGRAMMING;
            case MEDIA -> BuildScenario.MEDIA;
            case AI_INFERENCE -> BuildScenario.AI_INFERENCE;
            case RENDERING -> BuildScenario.CREATIVE;
        };
    }
}
