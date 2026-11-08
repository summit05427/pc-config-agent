package com.example.agent.shared.config;

import static org.springframework.security.config.Customizer.withDefaults;

import com.example.agent.shared.security.JwtKeyLoader;
import com.example.agent.shared.security.RestAccessDeniedHandler;
import com.example.agent.shared.security.RestAuthenticationEntryPoint;
import com.example.agent.shared.security.SecurityResponseWriter;
import com.example.agent.shared.security.TokenClaims;
import com.example.agent.shared.security.TokenUseFilter;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

/**
 * 安全配置：无状态 JWT 认证 + 基于角色的授权。
 *
 * <p>令牌算法固定 RS256：本服务用私钥签发，Agent 用公钥验签，
 * 两端都不允许算法协商降级，避免 {@code alg=none} 之类的伪造攻击。</p>
 *
 * <p>认证失败与权限不足统一交给 {@link RestAuthenticationEntryPoint} 与
 * {@link RestAccessDeniedHandler} 处理，保证 401/403 的响应体与业务接口一致。</p>
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@EnableConfigurationProperties(AppSecurityProperties.class)
@RequiredArgsConstructor
public class SecurityConfig {

    private static final String ROLE_PREFIX = "ROLE_";
    private static final String ROLES_CLAIM = "roles";
    private static final String SCOPE_PREFIX = "SCOPE_";
    private static final String SCOPE_MODEL_RUNTIME_READ = "SCOPE_model-runtime:read";
    private static final String SCOPE_MODEL_USAGE_WRITE = "SCOPE_model-usage:write";

    private final AppSecurityProperties properties;
    private final RestAuthenticationEntryPoint authenticationEntryPoint;
    private final RestAccessDeniedHandler accessDeniedHandler;
    private final SecurityResponseWriter securityResponseWriter;

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .cors(withDefaults())
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        // 登录、刷新、退出都靠「账号口令」或「HttpOnly Cookie」自证身份，
                        // 刷新与退出在服务端另有来源校验，因此无需访问令牌即可调用
                        .requestMatchers(HttpMethod.POST, "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout").permitAll()
                        // 服务令牌换取入口只接受 client 凭据，不能要求已认证
                        .requestMatchers(HttpMethod.POST, "/internal/v1/auth/service-token").permitAll()
                        .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                        // 运维端点免认证：Java 端口只绑回环，Nginx 不代理 /actuator，
                        // 采集器在容器网络内直连；不要让 Prometheus 依赖会过期的 JWT
                        .requestMatchers("/actuator/health", "/actuator/info", "/actuator/prometheus", "/error").permitAll()
                        .requestMatchers("/api/v1/admin/**").hasRole("ADMIN")
                        // 内部接口按 scope 细分：上报只需要写权限，其余需要读权限
                        .requestMatchers("/internal/v1/model-usage").hasAuthority(SCOPE_MODEL_USAGE_WRITE)
                        .requestMatchers("/internal/v1/**").hasAuthority(SCOPE_MODEL_RUNTIME_READ)
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
                        .authenticationEntryPoint(authenticationEntryPoint))
                .exceptionHandling(exception -> exception
                        .authenticationEntryPoint(authenticationEntryPoint)
                        .accessDeniedHandler(accessDeniedHandler))
                // 必须在 Resource Server 完成验签之后，才能读到 token_use
                .addFilterAfter(new TokenUseFilter(securityResponseWriter), BearerTokenAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        AppSecurityProperties.Jwt jwt = properties.getJwt();
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withPublicKey(JwtKeyLoader.loadPublicKey(jwt.getPublicKey()))
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                // 时间戳与 issuer 校验
                JwtValidators.createDefaultWithIssuer(jwt.getIssuer()),
                audienceValidator(jwt.getAudience())));
        return decoder;
    }

    @Bean
    JwtEncoder jwtEncoder() {
        AppSecurityProperties.Jwt jwt = properties.getJwt();
        RSAKey rsaKey = new RSAKey.Builder(JwtKeyLoader.loadPublicKey(jwt.getPublicKey()))
                .privateKey(JwtKeyLoader.loadPrivateKey(jwt.getPrivateKey()))
                .keyID(jwt.getKid())
                .algorithm(JWSAlgorithm.RS256)
                .build();
        return new NimbusJwtEncoder(new ImmutableJWKSet<SecurityContext>(new JWKSet(rsaKey)));
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(UserDetailsService userDetailsService, PasswordEncoder passwordEncoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        return new ProviderManager(provider);
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter rolesConverter = new JwtGrantedAuthoritiesConverter();
        rolesConverter.setAuthoritiesClaimName(ROLES_CLAIM);
        rolesConverter.setAuthorityPrefix(ROLE_PREFIX);
        JwtGrantedAuthoritiesConverter scopesConverter = new JwtGrantedAuthoritiesConverter();
        scopesConverter.setAuthoritiesClaimName(TokenClaims.SCOPE_CLAIM);
        scopesConverter.setAuthorityPrefix(SCOPE_PREFIX);
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        // 用户令牌只有 roles，服务令牌只有 scope；合并后授权规则可同时覆盖两类调用方
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> authorities = new ArrayList<>(rolesConverter.convert(jwt));
            authorities.addAll(scopesConverter.convert(jwt));
            return authorities;
        });
        return converter;
    }

    /**
     * 强制校验 {@code aud}：与 Agent 共享同一个受众值，防止本服务令牌被其他系统复用。
     */
    private OAuth2TokenValidator<Jwt> audienceValidator(String expectedAudience) {
        return token -> {
            List<String> audiences = token.getAudience();
            if (audiences != null && audiences.contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "令牌受众不匹配", null));
        };
    }
}
