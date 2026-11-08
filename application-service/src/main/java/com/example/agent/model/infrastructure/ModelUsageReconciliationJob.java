package com.example.agent.model.infrastructure;

import com.example.agent.model.application.ModelUsageReconciliationService;
import com.example.agent.shared.config.ModelRuntimeProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 模型用量定时对账任务。
 *
 * <p>cron 由配置注入，且显式按 UTC 触发：默认每日 00:05 UTC 对账前一自然日。
 * 若不指定 zone，Spring 会使用服务器默认时区，与台账的 UTC 自然日口径不一致。</p>
 */
@Component
@RequiredArgsConstructor
public class ModelUsageReconciliationJob {

    private final ModelUsageReconciliationService reconciliationService;
    private final ModelRuntimeProperties properties;

    /**
     * 按配置周期执行对账。
     */
    @Scheduled(cron = "${app.model.reconcile.cron}", zone = "UTC")
    public void reconcileDaily() {
        if (!properties.getReconcile().isEnabled()) {
            return;
        }
        reconciliationService.reconcile();
    }
}
