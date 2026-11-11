package com.example.agent.support;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * 用内存反馈持久化替换 MyBatis 实现，避免接口测试依赖真实数据库。
 */
@TestConfiguration(proxyBeanMethods = false)
public class InMemoryMessageFeedbackMapperConfig {

    @Bean
    @Primary
    InMemoryMessageFeedbackMapper inMemoryMessageFeedbackMapper() {
        return new InMemoryMessageFeedbackMapper();
    }
}
