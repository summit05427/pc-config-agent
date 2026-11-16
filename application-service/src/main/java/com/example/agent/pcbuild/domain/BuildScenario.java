package com.example.agent.pcbuild.domain;

import java.util.Locale;

/**
 * 场景权重：决定 CPU 与 GPU 跑分在总分中的占比。
 *
 * <p>权重之和固定为 100，评分全程使用整数运算，避免浮点误差导致同一输入排名漂移。</p>
 */
public enum BuildScenario {

    GAMING(30, 70),
    CREATIVE(55, 45),
    PROGRAMMING(80, 20),
    WORKSTATION(60, 40),
    OFFICE(85, 15),
    MEDIA(70, 30),
    BALANCED(50, 50),
    AI_INFERENCE(40, 60);

    private final int cpuWeight;
    private final int gpuWeight;

    BuildScenario(int cpuWeight, int gpuWeight) {
        this.cpuWeight = cpuWeight;
        this.gpuWeight = gpuWeight;
    }

    public int cpuWeight() {
        return cpuWeight;
    }

    public int gpuWeight() {
        return gpuWeight;
    }

    /**
     * 解析外部传入的场景名。
     *
     * @param raw 原始文本，可为 {@code null}
     * @return 命中场景；无法识别时为 {@code null}
     */
    public static BuildScenario parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        // Agent 侧按产品语义使用 video_editing / general_use 命名，这里做一次收敛
        return switch (normalized) {
            case "VIDEO_EDITING" -> CREATIVE;
            case "GENERAL_USE" -> BALANCED;
            case "GAMING" -> GAMING;
            case "CREATIVE" -> CREATIVE;
            case "PROGRAMMING" -> PROGRAMMING;
            case "WORKSTATION" -> WORKSTATION;
            case "OFFICE" -> OFFICE;
            case "MEDIA" -> MEDIA;
            case "BALANCED" -> BALANCED;
            case "AI_INFERENCE" -> AI_INFERENCE;
            default -> null;
        };
    }
}
