package com.example.agent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 启动类。
 *
 * <p>开启定时任务：刷新会话的过期清理由 {@code RefreshSessionCleanupJob} 承担，
 * 否则 {@code refresh_sessions} 会随登录次数无限增长。</p>
 */
@EnableScheduling
@SpringBootApplication
public class AgentApplicationServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentApplicationServiceApplication.class, args);
    }

}
