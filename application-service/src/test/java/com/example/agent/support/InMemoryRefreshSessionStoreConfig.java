package com.example.agent.support;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;

/**
 * 用内存实现替换刷新会话仓储，并禁用真实事务。
 *
 * <p>标 {@link Primary} 是因为生产实现 {@code MyBatisRefreshSessionStore} 仍是组件，
 * 测试容器里两个 Bean 同时存在，必须显式指定优先项。</p>
 *
 * <p>业务方法带 {@code @Transactional}：没有事务管理器时它会直接报错；
 * 有真实数据源时它会真的去连数据库，于是在没有数据库的测试里表现为 30 秒超时。
 * 内存仓储没有事务语义，这里注册一个空实现，既满足注解又不碰数据源。</p>
 */
@TestConfiguration(proxyBeanMethods = false)
public class InMemoryRefreshSessionStoreConfig {

    @Bean
    @Primary
    InMemoryRefreshSessionStore inMemoryRefreshSessionStore() {
        return new InMemoryRefreshSessionStore();
    }

    @Bean
    @Primary
    PlatformTransactionManager inMemoryTransactionManager() {
        return new NoOpTransactionManager();
    }

    /** 空事务管理器：仅让 {@code @Transactional} 注解不失败，不产生任何连接。 */
    static class NoOpTransactionManager extends AbstractPlatformTransactionManager {

        @Override
        protected Object doGetTransaction() {
            return new Object();
        }

        @Override
        protected void doBegin(Object transaction, TransactionDefinition definition) {
            // 内存仓储无事务语义，无需任何动作
        }

        @Override
        protected void doCommit(DefaultTransactionStatus status) {
            // 同上
        }

        @Override
        protected void doRollback(DefaultTransactionStatus status) {
            // 同上
        }
    }
}
