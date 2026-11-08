package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.shared.config.AppSecurityProperties;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 首次启动播种引导账号。
 *
 * <p>用户表落地后仍保留配置化的引导账号：模板与本地环境需要开箱可登录的账号，
 * 生产环境则由部署方通过环境变量提供口令（口令留空表示不创建该账号）。</p>
 *
 * <p>使用 {@link ApplicationRunner} 而不是 Bean 初始化钩子，确保执行时 Flyway
 * 已完成建表；已存在的用户名直接跳过，因此重复启动是幂等的。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class BootstrapUserSeeder implements ApplicationRunner {

    private final UserDirectory userDirectory;
    private final PasswordEncoder passwordEncoder;
    private final AppSecurityProperties properties;

    @Override
    public void run(ApplicationArguments args) {
        List<AppSecurityProperties.BootstrapUser> candidates = properties.getBootstrapUsers();
        for (AppSecurityProperties.BootstrapUser candidate : candidates) {
            seed(candidate);
        }
    }

    private void seed(AppSecurityProperties.BootstrapUser candidate) {
        String username = candidate.getUsername();
        if (candidate.getPassword() == null || candidate.getPassword().isBlank()) {
            log.info("引导账号未配置口令，跳过创建 username={}", username);
            return;
        }
        if (userDirectory.findByUsername(username).isPresent()) {
            return;
        }
        userDirectory.create(username, passwordEncoder.encode(candidate.getPassword()), candidate.getRoles());
        log.info("已创建引导账号 username={} roles={}", username, candidate.getRoles());
    }
}
