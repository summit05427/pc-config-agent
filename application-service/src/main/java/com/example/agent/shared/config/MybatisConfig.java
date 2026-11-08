package com.example.agent.shared.config;

import com.example.agent.shared.mybatis.UuidTypeHandler;
import java.util.UUID;
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MyBatis 全局装配。
 *
 * <p>只补充 MyBatis 缺失的 UUID 类型处理器：{@code postgres} 侧 {@code uuid} 列较多，
 * 逐个 SQL 手工转字符串会让映射代码到处是转换噪声。</p>
 */
@Configuration
public class MybatisConfig {

    /**
     * 注册 UUID 类型处理器，使行对象与 Mapper 入参可直接使用 {@link UUID}。
     *
     * @return MyBatis 配置定制器
     */
    @Bean
    ConfigurationCustomizer uuidTypeHandlerCustomizer() {
        return configuration -> configuration.getTypeHandlerRegistry()
                .register(UUID.class, new UuidTypeHandler());
    }
}
