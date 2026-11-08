package com.example.agent.identity.application;

/**
 * 登录失败限流端口。
 *
 * <p>调用顺序固定为「先 {@link #checkAllowed} → 认证 → 成功 {@link #clear} / 失败
 * {@link #recordFailure}」，限流只统计认证失败，成功登录会清零。</p>
 *
 * <p>当前实现是进程内计数，只能约束单实例；多实例部署时替换为 Redis 等共享存储实现，
 * 接口保持不变，业务代码无需修改。</p>
 */
public interface LoginAttemptLimiter {

    /**
     * 在认证前检查是否已被限制。
     *
     * @param clientIp 客户端 IP，无法解析时为 {@code null}
     * @param username 登录名
     * @throws com.example.agent.shared.error.BusinessException 超过失败上限时抛 429 {@code 10007}
     */
    void checkAllowed(String clientIp, String username);

    /**
     * 记录一次认证失败。
     *
     * @param clientIp 客户端 IP，无法解析时为 {@code null}
     * @param username 登录名
     */
    void recordFailure(String clientIp, String username);

    /**
     * 成功登录后清零计数。
     *
     * @param clientIp 客户端 IP，无法解析时为 {@code null}
     * @param username 登录名
     */
    void clear(String clientIp, String username);
}
