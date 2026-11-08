package com.example.agent.pcbuild.domain;

import java.util.List;
import java.util.Locale;

/**
 * 一套完整配置必需的八个硬件类别。
 *
 * <p>声明顺序同时是求解器的确定性枚举顺序：任何依赖类别的循环都必须按该顺序遍历，
 * 不能依赖 {@code HashMap} 的迭代顺序。</p>
 */
public enum HardwareCategory {

    CPU,
    MOTHERBOARD,
    MEMORY,
    GPU,
    PSU,
    CASE,
    COOLER,
    STORAGE;

    /** 一套完整配置的固定类别集合，顺序与求解顺序一致。 */
    public static final List<HardwareCategory> REQUIRED_CATEGORIES = List.of(values());

    /**
     * 解析外部传入的类别名，忽略大小写并把连字符与空格归一化为下划线。
     *
     * @param raw 原始文本，可为 {@code null}
     * @return 命中类别；无法识别时为 {@code null}
     */
    public static HardwareCategory parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String normalized = raw.trim().toUpperCase(Locale.ROOT).replace('-', '_').replace(' ', '_');
        for (HardwareCategory category : values()) {
            if (category.name().equals(normalized)) {
                return category;
            }
        }
        return null;
    }

    /**
     * @return 供日志与响应使用的稳定小写标识
     */
    public String code() {
        return name().toLowerCase(Locale.ROOT);
    }
}
