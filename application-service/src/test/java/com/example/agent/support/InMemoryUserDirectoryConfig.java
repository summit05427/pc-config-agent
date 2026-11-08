package com.example.agent.support;

import com.example.agent.identity.application.UserDirectory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;

/**
 * 用内存实现替换数据库用户源，让启动 Spring 容器的测试不需要真实数据库。
 *
 * <p>标 {@link Primary} 是因为生产实现 {@code MyBatisUserDirectory} 仍是组件，
 * 测试容器里两个 Bean 同时存在，必须显式指定优先项。</p>
 */
@TestConfiguration(proxyBeanMethods = false)
public class InMemoryUserDirectoryConfig {

    @Bean
    @Primary
    UserDirectory inMemoryUserDirectory() {
        return new InMemoryUserDirectory();
    }
}
