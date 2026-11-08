package com.example.agent.shared.config;

import java.time.Duration;
import java.util.List;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 跨域配置。
 *
 * <p>{@code allowedOrigins} 默认为空，表示不放开任何跨域来源，避免生产环境误开；
 * 需要跨域访问时通过配置项或环境变量显式声明白名单。</p>
 */
@Getter
@Setter
@Validated
@ConfigurationProperties(prefix = "app.cors")
public class CorsProperties {

    private List<String> allowedOrigins = List.of();

    private List<String> allowedMethods = List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS");

    private List<String> allowedHeaders = List.of("*");

    private List<String> exposedHeaders = List.of("X-Request-Id");

    private boolean allowCredentials = false;

    private Duration maxAge = Duration.ofHours(1);
}
