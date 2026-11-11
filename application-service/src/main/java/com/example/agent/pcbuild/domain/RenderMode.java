package com.example.agent.pcbuild.domain;

import java.util.Locale;

/**
 * 渲染/计算侧重的硬件取向。
 *
 * <p>用于「渲染」类工作负载按用户实际用途调整权重：同样的工作负载，
 * 偏 CPU 渲染与偏 GPU 渲染应当给出不同权重组合。</p>
 */
public enum RenderMode {

    CPU,
    GPU,
    BOTH;

    /**
     * 解析外部传入的渲染模式。
     *
     * <p>忽略大小写；空值或无法识别时返回 {@code null}，由调用方决定默认值，
     * 避免把非法输入静默当成 {@code BOTH}。</p>
     *
     * @param raw 原始文本，可为 {@code null}
     * @return 命中模式；无法识别时为 {@code null}
     */
    public static RenderMode parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "CPU" -> CPU;
            case "GPU" -> GPU;
            case "BOTH" -> BOTH;
            default -> null;
        };
    }
}
