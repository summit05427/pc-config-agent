package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.LoginAttemptLimiter;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 进程内登录失败限流。
 *
 * <p>按「IP + 登录名」计数，窗口内失败达到上限后直接拒绝，成功登录清零。
 * 计数只存内存、重启即清空，因此只适用于单实例部署；多实例需要改用共享存储，
 * 否则各实例独立计数会让实际上限成倍放大。</p>
 *
 * <p>只保留窗口内的少量条目，并用阈值触发过期清理，避免恶意请求把内存撑大。</p>
 */
@Component
public class InMemoryLoginAttemptLimiter implements LoginAttemptLimiter {

    static final int MAX_ATTEMPTS = 5;

    static final Duration WINDOW = Duration.ofSeconds(60);

    /** 超过该条目数时触发一次过期清理，清理本身是 O(n)，高频触发会影响登录延迟。 */
    private static final int CLEANUP_THRESHOLD = 10_000;

    private static final String UNKNOWN_IP = "unknown";

    private final Clock clock;

    private final Map<String, AttemptWindow> windows = new ConcurrentHashMap<>();

    public InMemoryLoginAttemptLimiter() {
        this(Clock.systemUTC());
    }

    InMemoryLoginAttemptLimiter(Clock clock) {
        this.clock = clock;
    }

    @Override
    public void checkAllowed(String clientIp, String username) {
        AttemptWindow window = windows.get(composeKey(clientIp, username));
        if (window == null) {
            return;
        }
        Instant now = clock.instant();
        if (!window.isExpired(now) && window.failedAttempts() >= MAX_ATTEMPTS) {
            throw new BusinessException(CommonErrorCode.TOO_MANY_REQUESTS);
        }
    }

    @Override
    public void recordFailure(String clientIp, String username) {
        evictExpired();
        String key = composeKey(clientIp, username);
        Instant now = clock.instant();
        windows.compute(key, (ignored, existing) -> {
            if (existing == null || existing.isExpired(now)) {
                return new AttemptWindow(1, now.plus(WINDOW));
            }
            return new AttemptWindow(existing.failedAttempts() + 1, existing.expiresAt());
        });
    }

    @Override
    public void clear(String clientIp, String username) {
        windows.remove(composeKey(clientIp, username));
    }

    private void evictExpired() {
        if (windows.size() < CLEANUP_THRESHOLD) {
            return;
        }
        Instant now = clock.instant();
        windows.values().removeIf(window -> window.isExpired(now));
    }

    private static String composeKey(String clientIp, String username) {
        String ip = clientIp == null || clientIp.isBlank() ? UNKNOWN_IP : clientIp;
        String account = username == null ? "" : username.toLowerCase(Locale.ROOT);
        return ip + "|" + account;
    }

    /**
     * 窗口计数；不可变，更新时整体替换，避免并发下的部分可见状态。
     *
     * @param failedAttempts 当前窗口内失败次数
     * @param expiresAt      窗口结束时间
     */
    private record AttemptWindow(int failedAttempts, Instant expiresAt) {

        boolean isExpired(Instant now) {
            return !now.isBefore(expiresAt);
        }
    }
}
