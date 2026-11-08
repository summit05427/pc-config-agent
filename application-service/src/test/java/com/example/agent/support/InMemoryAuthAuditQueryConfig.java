package com.example.agent.support;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * 用内存审计查询替换数据库实现。
 *
 * <p>标 {@link Primary} 是因为生产实现 {@code MyBatisAuthAuditQuery} 仍是组件，
 * 两个 Bean 同时存在时必须显式指定优先项。</p>
 */
@TestConfiguration(proxyBeanMethods = false)
public class InMemoryAuthAuditQueryConfig {

    @Bean
    @Primary
    InMemoryAuthAuditQuery inMemoryAuthAuditQuery() {
        return new InMemoryAuthAuditQuery();
    }
}
