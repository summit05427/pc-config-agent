package com.example.agent.model.infrastructure;

import com.example.agent.model.application.ModelRuntimeService;
import com.example.agent.shared.config.ModelRuntimeProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 过期运行时任务清理任务。
 *
 * <p>只把到期任务标记为 EXPIRED，不删除任务行：使用明细通过 {@code task_id} 外键
 * 引用任务，删除会让历史台账失去归属。显式按 UTC 触发，与台账的 UTC 口径一致。</p>
 */
@Component
@RequiredArgsConstructor
public class ModelRuntimeTaskCleanupJob {

    private final ModelRuntimeService modelRuntimeService;
    private final ModelRuntimeProperties properties;

    /**
     * 按配置周期标记过期任务。
     */
    @Scheduled(cron = "${app.model.task-cleanup.cron}", zone = "UTC")
    public void expireStaleTasks() {
        if (!properties.getTaskCleanup().isEnabled()) {
            return;
        }
        modelRuntimeService.expireStaleTasks();
    }
}
