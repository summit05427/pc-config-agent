package com.example.agent.model.application;

import com.example.agent.model.domain.ModelReference;
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
 * 平台托管密钥可用性探测。
 *
 * <p>为什么不只看配置是否非空：{@code LLM_API_KEY} 可能已经过期或在 Provider 侧被删除，
 * 仅凭「变量存在」就把平台模型展示给用户，会让用户选中一个必然失败的模型。这里复用
 * 网关的 {@code probe:<provider>} 部署做一次真实调用：请求体不带 {@code api_key}，
 * 网关会使用平台自己的密钥，因此 401/403 就代表平台托管不可用。</p>
 *
 * <p>探测结果按 {@link ModelRuntimeProperties#getManagedProbeTtl()} 缓存；上游鉴权失败时
 * 由使用明细回写调用 {@link #markUnavailable()} 立即失效，避免继续放行。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ManagedModelAvailability {

    private static final String PATH_CHAT_COMPLETIONS = "/v1/chat/completions";

    private static final String AUTHORIZATION_PREFIX = "Bearer ";

    private static final String CONTENT_TYPE_JSON = "application/json";

    private static final String PROBE_MODEL_PREFIX = "probe:";

    private static final String PROBE_PROMPT = "ping";

    private final HttpClient modelGatewayHttpClient;
    private final ModelRuntimeProperties properties;
    private final ObjectMapper objectMapper;

    private volatile boolean cachedAvailable;
    private volatile long expiresAtNanos;

    /**
     * 平台托管是否可用。
     *
     * <p>失败关闭（fail-closed）：未配置、超时、网关不可达、上游拒绝都按不可用处理。
     * 首次调用会同步探测一次，耗时受凭证验证超时约束。</p>
     *
     * @return 平台密钥真实可用时为 {@code true}
     */
    public synchronized boolean isAvailable() {
        if (!properties.isManagedEnabled() || !properties.isRuntimeEnabled()) {
            return false;
        }
        long now = System.nanoTime();
        if (expiresAtNanos > now) {
            return cachedAvailable;
        }
        boolean available = probe();
        cachedAvailable = available;
        expiresAtNanos = now + properties.getManagedProbeTtl().toNanos();
        return available;
    }

    /**
     * 平台模型调用出现鉴权失败时立即失效缓存，下一次目录/建任务会重新探测并隐藏平台模型。
     */
    public synchronized void markUnavailable() {
        cachedAvailable = false;
        expiresAtNanos = System.nanoTime() + properties.getManagedProbeTtl().toNanos();
    }

    private boolean probe() {
        String masterKey = properties.getGateway().getMasterKey();
        if (masterKey == null || masterKey.isBlank()) {
            log.warn("模型网关主密钥未配置，平台托管按不可用处理");
            return false;
        }
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(gatewayUrl()))
                .timeout(timeout())
                .header("Authorization", AUTHORIZATION_PREFIX + masterKey.trim())
                .header("Content-Type", CONTENT_TYPE_JSON)
                .header("Accept", CONTENT_TYPE_JSON)
                .POST(HttpRequest.BodyPublishers.ofString(requestBody()))
                .build();
        try {
            int status = modelGatewayHttpClient
                    .send(request, HttpResponse.BodyHandlers.discarding())
                    .statusCode();
            boolean available = status >= 200 && status < 300;
            if (!available) {
                log.warn("平台托管密钥探测未通过 status={}", status);
            }
            return available;
        } catch (IOException ex) {
            log.warn("平台托管密钥探测请求失败，按不可用处理 reason={}", ex.getClass().getSimpleName());
            return false;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.warn("平台托管密钥探测被中断，按不可用处理");
            return false;
        }
    }

    /**
     * 使用默认模型的 Provider 探测，确保探测路径与真实对话使用的部署一致。
     */
    private String requestBody() {
        String providerCode = ModelReference.parse(properties.getDefaultModelKey()).provider();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", PROBE_MODEL_PREFIX + providerCode);
        payload.put("messages", List.of(Map.of("role", "user", "content", PROBE_PROMPT)));
        payload.put("max_tokens", 1);
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
}
