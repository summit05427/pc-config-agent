package com.example.agent.pcbuild.domain;

/**
 * 兼容性规则结论。
 *
 * <p>{@code UNKNOWN} 是本模型的一等状态：参数缺失时必须返回它，既不能当作
 * {@code PASS} 展示，也不能跳过规则。求解器只把 {@code FAIL} 当作硬冲突。</p>
 */
public enum CompatibilityStatus {

    PASS,
    WARNING,
    FAIL,
    UNKNOWN;

    /**
     * 合并多个结论时取最严重者，优先级 {@code FAIL > UNKNOWN > WARNING > PASS}。
     *
     * @param left  左值
     * @param right 右值
     * @return 更严重的状态
     */
    public static CompatibilityStatus worst(CompatibilityStatus left, CompatibilityStatus right) {
        return left.rank() >= right.rank() ? left : right;
    }

    private int rank() {
        return switch (this) {
            case FAIL -> 3;
            case UNKNOWN -> 2;
            case WARNING -> 1;
            case PASS -> 0;
        };
    }
}
