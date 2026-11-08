package com.example.agent.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

/**
 * 进程内登录限流单元测试：上限、窗口重置、成功清零与维度隔离。
 */
class InMemoryLoginAttemptLimiterTests {

    private static final String IP = "10.0.0.1";
    private static final String USERNAME = "admin";

    private final MutableClock clock = new MutableClock();

    private final InMemoryLoginAttemptLimiter limiter = new InMemoryLoginAttemptLimiter(clock);

    @Test
    void checkAllowed_whenNoFailure_allowsLogin() {
        assertThatCode(() -> limiter.checkAllowed(IP, USERNAME)).doesNotThrowAnyException();
    }

    @Test
    void checkAllowed_afterMaxAttempts_blocksUntilWindowExpires() {
        for (int attempt = 0; attempt < InMemoryLoginAttemptLimiter.MAX_ATTEMPTS; attempt++) {
            limiter.recordFailure(IP, USERNAME);
        }

        assertThatThrownBy(() -> limiter.checkAllowed(IP, USERNAME))
                .isInstanceOf(BusinessException.class)
                .satisfies(ex -> assertThat(((BusinessException) ex).getErrorCode())
                        .isEqualTo(CommonErrorCode.TOO_MANY_REQUESTS));

        clock.advance(InMemoryLoginAttemptLimiter.WINDOW);
        assertThatCode(() -> limiter.checkAllowed(IP, USERNAME)).doesNotThrowAnyException();
    }

    @Test
    void recordFailure_whenOldWindowExpired_startsFreshCounter() {
        limiter.recordFailure(IP, USERNAME);
        clock.advance(InMemoryLoginAttemptLimiter.WINDOW);

        limiter.recordFailure(IP, USERNAME);

        // 新窗口只有 1 次失败，仍可继续尝试
        assertThatCode(() -> limiter.checkAllowed(IP, USERNAME)).doesNotThrowAnyException();
    }

    @Test
    void clear_afterSuccessfulLogin_resetsCounter() {
        for (int attempt = 0; attempt < InMemoryLoginAttemptLimiter.MAX_ATTEMPTS; attempt++) {
            limiter.recordFailure(IP, USERNAME);
        }
        limiter.clear(IP, USERNAME);

        assertThatCode(() -> limiter.checkAllowed(IP, USERNAME)).doesNotThrowAnyException();
    }

    @Test
    void recordFailure_isIsolatedByIpAndUsername() {
        for (int attempt = 0; attempt < InMemoryLoginAttemptLimiter.MAX_ATTEMPTS; attempt++) {
            limiter.recordFailure(IP, USERNAME);
        }

        // 换 IP、换账号都不应受同一份计数影响
        assertThatCode(() -> limiter.checkAllowed("10.0.0.2", USERNAME)).doesNotThrowAnyException();
        assertThatCode(() -> limiter.checkAllowed(IP, "another-user")).doesNotThrowAnyException();
    }

    /**
     * 可推进的时钟，避免测试依赖真实时间休眠。
     */
    private static final class MutableClock extends Clock {

        private Instant current = Instant.parse("2026-10-31T00:00:00Z");

        void advance(Duration duration) {
            current = current.plus(duration);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return current;
        }
    }
}
