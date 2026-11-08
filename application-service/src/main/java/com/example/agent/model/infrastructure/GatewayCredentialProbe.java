package com.example.agent.model.infrastructure;

import com.example.agent.shared.config.ModelRuntimeProperties;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 经模型网关做凭证连通性探测。
 *
 * <p>Java 不再理解 Provider 协议：只向 LiteLLM 的 OpenAI 兼容端点发一次
 * {@code max_tokens=1} 的请求，由网关按 {@code probe:<providerCode>} 选择部署。
 * 用户密钥放在请求体 {@code api_key} 中，属于网关的请求级凭证，仅本次请求生效，
 * 不落网关存储。自定义 {@code api_base} 仍由 Java 做 SSRF 校验后才下发。</p>
 *
 * <p>只返回结果分类；日志不记录密钥、请求体或响应体。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class GatewayCredentialProbe {

    static final String PATH_CHAT_COMPLETIONS = "/v1/chat/completions";

    private static final String AUTHORIZATION_PREFIX = "Bearer ";

    private static final String CONTENT_TYPE_JSON = "application/json";

    private static final String PROBE_MODEL_PREFIX = "probe:";

    private static final String PROBE_PROMPT = "ping";

    /** 网络失败时使用的哨兵状态码，避免把 IO 异常穿透成业务异常。 */
    private static final int NETWORK_FAILURE_STATUS = 0;

    private final HttpClient modelGatewayHttpClient;
    private final ModelRuntimeProperties properties;
    private final OutboundHostGuard outboundHostGuard;
    private final ObjectMapper objectMapper;

    /**
     * 探测凭证可用性。
     *
     * @param providerCode Provider 代码，用于拼出网关的探测模型名
     * @param baseUrl      连接保存的接入地址；为空表示由网关使用官方默认地址
     * @param apiKey       解密后的明文密钥，只在本方法内使用
     * @return 探测结果分类
     * @throws com.example.agent.shared.error.BusinessException 自定义地址未通过 SSRF 校验时 400
     */
    public Outcome probe(String providerCode, String baseUrl, String apiKey) {
        String masterKey = properties.getGateway().getMasterKey();
        if (masterKey == null || masterKey.isBlank()) {
            // 未部署网关时不能把「探测不了」静默当成验证通过
            log.warn("模型网关主密钥未配置，凭证探测按不可用处理 provider={}", providerCode);
            return Outcome.UNAVAILABLE;
        }
        String normalizedBaseUrl = normalizeBaseUrl(baseUrl);
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(gatewayUrl()))
                .timeout(timeout())
                .header("Authorization", AUTHORIZATION_PREFIX + masterKey.trim())
                .header("Content-Type", CONTENT_TYPE_JSON)
                .header("Accept", CONTENT_TYPE_JSON)
                .POST(HttpRequest.BodyPublishers.ofString(requestBody(providerCode, normalizedBaseUrl, apiKey)))
                .build();
        return classify(providerCode, send(providerCode, request));
    }

    /**
     * 只在用户填了自定义地址时校验：为空表示走网关内置的官方地址，无需 SSRF 检查。
     */
    private String normalizeBaseUrl(String baseUrl) {
        String candidate = baseUrl == null ? "" : baseUrl.trim();
        return candidate.isEmpty() ? "" : outboundHostGuard.validate(candidate);
    }

    private String requestBody(String providerCode, String baseUrl, String apiKey) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", PROBE_MODEL_PREFIX + providerCode);
        payload.put("messages", List.of(Map.of("role", "user", "content", PROBE_PROMPT)));
        payload.put("max_tokens", 1);
        // clientside credentials：请求体 api_key 只替换本次请求的部署密钥
        payload.put("api_key", apiKey);
        if (!baseUrl.isEmpty()) {
            payload.put("api_base", baseUrl);
        }
        return objectMapper.writeValueAsString(payload);
    }

    private String gatewayUrl() {
        String baseUrl = properties.getGateway().getBaseUrl().trim();
        String normalized = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        return normalized + PATH_CHAT_COMPLETIONS;
    }

    private Duration timeout() {
        return properties.getCredential().getVerifyTimeout();
    }

    private Outcome classify(String providerCode, int statusCode) {
        if (statusCode >= 200 && statusCode < 300) {
            return Outcome.VERIFIED;
        }
        if (statusCode == 401 || statusCode == 403) {
            return Outcome.REJECTED;
        }
        log.warn("网关凭证探测未通过 provider={} outcome={}", providerCode, Outcome.UNAVAILABLE);
        return Outcome.UNAVAILABLE;
    }

    private int send(String providerCode, HttpRequest request) {
        try {
            return modelGatewayHttpClient
                    .send(request, HttpResponse.BodyHandlers.discarding())
                    .statusCode();
        } catch (IOException ex) {
            // 只记录异常类型，避免异常消息中可能出现的地址或凭证细节
            log.warn("网关凭证探测请求失败，按不可用处理 provider={} reason={}",
                    providerCode, ex.getClass().getSimpleName());
            return NETWORK_FAILURE_STATUS;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.warn("网关凭证探测被中断，按不可用处理 provider={} reason={}",
                    providerCode, ex.getClass().getSimpleName());
            return NETWORK_FAILURE_STATUS;
        }
    }

    /**
     * 探测结果分类。
     */
    public enum Outcome {

        /** 凭证可用。 */
        VERIFIED,

        /** 网关明确拒绝凭证（401/403）。 */
        REJECTED,

        /** 网关不可达、超时、未配置主密钥或返回非预期状态。 */
        UNAVAILABLE
    }
}
