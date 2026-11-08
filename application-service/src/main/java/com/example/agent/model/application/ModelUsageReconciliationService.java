package com.example.agent.model.application;

import com.example.agent.model.domain.ReconciliationResult;
import com.example.agent.model.infrastructure.QuotaMapper;
import com.example.agent.model.infrastructure.UsageMapper;
import com.example.agent.shared.config.ModelRuntimeProperties;
import java.time.Clock;
import java.time.LocalDate;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 模型用量对账。
 *
 * <p>只做只读统计，不修改台账。额度溢出与归属不一致属于「本不应发生」的
 * 不变量破坏，记 {@code ERROR}；达到上限与负数费用属于可恢复异常，记 {@code WARN}。
 * 日志只输出计数，不输出用户标识，避免告警通道泄露用户维度信息。</p>
 *
 * <p>统计对象是<b>前一 UTC 自然日</b>：任务默认在 UTC 00:05 触发，此时当日刚开始，
 * 若统计当日只会得到空结果；前一日的额度行与用量记录才是完整的一天。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ModelUsageReconciliationService {

    private final UsageMapper usageMapper;
    private final QuotaMapper quotaMapper;
    private final ModelRuntimeProperties properties;
    private final Clock modelRuntimeUtcClock;

    /**
     * 执行一次对账。
     *
     * @return 对账统计；运行时关闭时返回 {@link ReconciliationResult#skipped()}
     */
    @Transactional(readOnly = true)
    public ReconciliationResult reconcile() {
        if (!properties.isRuntimeEnabled()) {
            return ReconciliationResult.skipped();
        }
        // 对账完整自然日而非「今天」：任务在 UTC 00:05 触发，当日数据尚不存在
        LocalDate quotaDate = LocalDate.now(modelRuntimeUtcClock).minusDays(1);
        int overflowUsers = quotaMapper.countOverflow(quotaDate);
        int atLimitUsers = quotaMapper.countAtLimit(quotaDate);
        int attributionMismatches = usageMapper.countAttributionMismatches();
        int negativeCost = usageMapper.countNegativeEstimatedCost();
        int costStatusMismatches = usageMapper.countCostStatusMismatches();
        if (overflowUsers > 0) {
            log.error("模型额度对账异常：已用数超过上限 quotaDate={} users={}", quotaDate, overflowUsers);
        }
        if (attributionMismatches > 0) {
            log.error("模型用量对账异常：明细归属与任务不一致 records={}", attributionMismatches);
        }
        if (costStatusMismatches > 0) {
            log.error("模型用量对账异常：成本状态与金额/币种不一致 records={}", costStatusMismatches);
        }
        if (atLimitUsers > 0) {
            log.warn("模型额度告警：当日额度已用满 quotaDate={} users={}", quotaDate, atLimitUsers);
        }
        if (negativeCost > 0) {
            log.warn("模型用量对账告警：费用估算为负数 records={}", negativeCost);
        }
        return new ReconciliationResult(
                true, overflowUsers, atLimitUsers, attributionMismatches, negativeCost, costStatusMismatches);
    }
}
