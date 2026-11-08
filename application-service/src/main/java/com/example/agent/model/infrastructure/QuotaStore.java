package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.QuotaSnapshot;
import java.time.LocalDate;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 每日请求额度读写入口。
 *
 * <p>扣减仍由单语句原子完成，这里不做「先查后改」。</p>
 */
@Component
@RequiredArgsConstructor
public class QuotaStore {

    private final QuotaMapper quotaMapper;

    /**
     * 原子占用一次额度。
     *
     * @return 扣减后的快照；{@code null} 表示当日额度已满、本次未扣减
     */
    public QuotaSnapshot tryConsume(UUID userPublicId, LocalDate quotaDate, int dailyLimit) {
        return toSnapshot(quotaMapper.tryConsume(userPublicId, quotaDate, dailyLimit));
    }

    public QuotaSnapshot find(UUID userPublicId, LocalDate quotaDate) {
        return toSnapshot(quotaMapper.find(userPublicId, quotaDate));
    }

    private static QuotaSnapshot toSnapshot(QuotaRow row) {
        return row == null ? null : new QuotaSnapshot(row.usedCount(), row.limitCount());
    }
}
