package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.util.ArrayDeque;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 凭证验证端点的单用户滑动窗口限流。
 *
 * <p>验证会发起真实出站请求，不限制会变成低成本探测入口。限流状态放在进程内，
 * 单实例部署足够；多实例时需要替换为 Redis 等共享存储，否则每个实例各自计数。</p>
 */
@Component
@RequiredArgsConstructor
public class ModelCredentialVerifyRateLimiter {

    private static final long WINDOW_MILLIS = 60_000L;

    private static final int CLEANUP_THRESHOLD = 10_000;

    private final ModelRuntimeProperties properties;

    private final Map<UUID, ArrayDeque<Long>> attempts = new ConcurrentHashMap<>();

    /**
     * 校验并记录一次验证尝试。
     *
     * @param userPublicId 用户公开 ID
     * @throws BusinessException 超过每分钟上限时 429 {@code 40222}
     */
    public void requireAllowed(UUID userPublicId) {
        long now = System.currentTimeMillis();
        long windowStart = now - WINDOW_MILLIS;
        ArrayDeque<Long> userAttempts = attempts.computeIfAbsent(userPublicId, key -> new ArrayDeque<>());
        synchronized (userAttempts) {
            while (!userAttempts.isEmpty() && userAttempts.peekFirst() < windowStart) {
                userAttempts.pollFirst();
            }
            int limit = properties.getCredential().getVerifyRateLimitPerMinute();
            if (userAttempts.size() >= limit) {
                throw new BusinessException(ModelErrorCode.CREDENTIAL_VERIFY_RATE_LIMITED);
            }
            userAttempts.addLast(now);
        }
        if (attempts.size() > CLEANUP_THRESHOLD) {
            cleanup(windowStart);
        }
    }

    private void cleanup(long windowStart) {
        attempts.entrySet().removeIf(entry -> {
            ArrayDeque<Long> userAttempts = entry.getValue();
            synchronized (userAttempts) {
                while (!userAttempts.isEmpty() && userAttempts.peekFirst() < windowStart) {
                    userAttempts.pollFirst();
                }
                return userAttempts.isEmpty();
            }
        });
    }
}
