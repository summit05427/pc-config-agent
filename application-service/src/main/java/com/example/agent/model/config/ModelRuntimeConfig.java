package com.example.agent.model.config;

import com.example.agent.shared.config.ModelRuntimeProperties;
import java.net.http.HttpClient;
import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 模型模块装配。
 *
 * <p>UTC 时钟单独注入：额度按 UTC 自然日统计，用固定时钟才能在测试中验证日界。</p>
 */
@Configuration
@EnableConfigurationProperties(ModelRuntimeProperties.class)
public class ModelRuntimeConfig {

    @Bean
    Clock modelRuntimeUtcClock() {
        return Clock.systemUTC();
    }

    /**
     * 模型网关探测专用 HTTP 客户端。
     *
     * <p>禁用自动重定向：重定向目标可能是私网地址，跟着跳转会绕过接入地址校验。
     * 连接超时与请求超时共用 {@code model.credential.verify-timeout}，避免两端取值
     * 不一致导致慢网络下连接阶段先失败、配置调大后仍不生效。</p>
     */
    @Bean
    HttpClient modelGatewayHttpClient(ModelRuntimeProperties properties) {
        return HttpClient.newBuilder()
                .connectTimeout(properties.getCredential().getVerifyTimeout())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }
}
