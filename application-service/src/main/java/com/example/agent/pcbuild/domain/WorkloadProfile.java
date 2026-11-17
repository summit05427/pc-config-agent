package com.example.agent.pcbuild.domain;

/**
 * 工作负载画像。
 *
 * <p>画像表达「用户要做什么」，Java 只保留它到 {@link BuildScenario}（CPU/GPU 权重）的映射，
 * 供草稿评分与结果解释使用；候选排序与选型由 Agent 负责。</p>
 */
public enum WorkloadProfile {

    GENERAL,
    GAMING,
    VIDEO_EDITING,
    PROGRAMMING,
    RENDERING,
    MEDIA,
    AI_INFERENCE;

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
