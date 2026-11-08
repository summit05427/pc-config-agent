package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.RefreshSessionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 刷新会话清理任务。
 *
 * <p>撤销只是标记，行会一直保留：过期会话留在表里便于排查「用户为什么被强制重登」。
 * 每天凌晨清一次，只删除绝对过期已超过保留期的历史行，避免表无限增长。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RefreshSessionCleanupJob {

    private final RefreshSessionService refreshSessionService;

    @Scheduled(cron = "0 30 3 * * *")
    public void purgeExpiredSessions() {
        int deleted = refreshSessionService.purgeExpired();
        if (deleted > 0) {
            log.info("清理解除过期刷新会话完成, deleted={}", deleted);
        }
    }
}
