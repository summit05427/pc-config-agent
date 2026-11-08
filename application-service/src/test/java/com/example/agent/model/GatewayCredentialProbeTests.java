package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.GatewayCredentialProbe;
import com.example.agent.model.infrastructure.OutboundHostGuard;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

/**
 * 网关凭证探测单测：用 mock {@link HttpClient} 覆盖状态码分类，不发起真实网络请求。
 *
 * <p>探测约定是「一次 POST 网关 chat/completions，由请求体 api_key 提供用户凭证」，
 * 因此这里同时断言请求地址、鉴权头与请求体字段。</p>
 */
@ExtendWith(MockitoExtension.class)
class GatewayCredentialProbeTests {

    private static final String PROVIDER_CODE = "openai";

    private static final String BASE_URL = "https://api.example.com/v1";

    private static final String GATEWAY_BASE_URL = "http://127.0.0.1:4000";

    private static final String MASTER_KEY = "sk-master-1234567890";

    private static final String SECRET = "sk-test-1234567890";

    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    @Mock
    private HttpClient client;

    @Mock
    private OutboundHostGuard outboundHostGuard;

    private ModelRuntimeProperties properties;

    private GatewayCredentialProbe probe;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.getCredential().setVerifyTimeout(TIMEOUT);
        properties.getGateway().setBaseUrl(GATEWAY_BASE_URL);
        properties.getGateway().setMasterKey(MASTER_KEY);
        probe = new GatewayCredentialProbe(
                client, properties, outboundHostGuard, JsonMapper.builder().build());
    }

    @Test
    void probe_shouldReturnVerifiedAndSendGatewayRequest() throws Exception {
        when(outboundHostGuard.validate(BASE_URL)).thenReturn(BASE_URL);
        whenResponse(200);

        assertThat(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.VERIFIED);

        ArgumentCaptor<HttpRequest> captor = ArgumentCaptor.forClass(HttpRequest.class);
        verify(client).send(captor.capture(), anyHandler());
        HttpRequest request = captor.getValue();
        assertThat(request.uri().toString()).isEqualTo(GATEWAY_BASE_URL + "/v1/chat/completions");
        assertThat(request.method()).isEqualTo("POST");
        assertThat(request.headers().firstValue("Authorization")).contains("Bearer " + MASTER_KEY);
        assertThat(request.headers().firstValue("Content-Type")).contains("application/json");
        assertThat(request.timeout()).contains(TIMEOUT);

        String body = requestBody(request);
        assertThat(body)
                .contains("\"model\":\"probe:" + PROVIDER_CODE + "\"")
                .contains("\"max_tokens\":1")
                .contains("\"api_key\":\"" + SECRET + "\"")
                .contains("\"api_base\":\"" + BASE_URL + "\"");
    }

    @Test
    void probe_shouldReturnRejected_whenGatewayRefusesCredential() throws Exception {
        when(outboundHostGuard.validate(BASE_URL)).thenReturn(BASE_URL);
        whenResponse(401);

        assertThat(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.REJECTED);
    }

    @Test
    void probe_shouldReturnUnavailable_whenGatewayReturnsServerError() throws Exception {
        when(outboundHostGuard.validate(BASE_URL)).thenReturn(BASE_URL);
        whenResponse(500);

        assertThat(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.UNAVAILABLE);
    }

    @Test
    void probe_shouldReturnUnavailable_whenNetworkFails() throws Exception {
        when(outboundHostGuard.validate(BASE_URL)).thenReturn(BASE_URL);
        when(client.send(any(HttpRequest.class), anyHandler())).thenThrow(new IOException("unreachable"));

        assertThat(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.UNAVAILABLE);
    }

    @Test
    void probe_shouldSkipGuardAndOmitApiBase_whenBaseUrlIsEmpty() throws Exception {
        whenResponse(200);

        assertThat(probe.probe(PROVIDER_CODE, "", SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.VERIFIED);

        // 空地址表示走网关内置的官方地址，Java 不做 SSRF 校验
        verifyNoInteractions(outboundHostGuard);
        ArgumentCaptor<HttpRequest> captor = ArgumentCaptor.forClass(HttpRequest.class);
        verify(client).send(captor.capture(), anyHandler());
        assertThat(requestBody(captor.getValue())).doesNotContain("api_base");
    }

    @Test
    void probe_shouldPropagateSecurityException_whenBaseUrlIsRejected() {
        when(outboundHostGuard.validate("http://127.0.0.1/v1"))
                .thenThrow(new BusinessException(ModelErrorCode.BASE_URL_INVALID));

        assertThatThrownBy(() -> probe.probe(PROVIDER_CODE, "http://127.0.0.1/v1", SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        verifyNoInteractions(client);
    }

    @Test
    void probe_shouldReturnUnavailableWithoutSending_whenMasterKeyIsMissing() {
        properties.getGateway().setMasterKey("");

        assertThat(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .isEqualTo(GatewayCredentialProbe.Outcome.UNAVAILABLE);
        verifyNoInteractions(client, outboundHostGuard);
    }

    private void whenResponse(int statusCode) throws Exception {
        // 先构造响应再开启 when：Mockito 禁止在未完成的桩里对其它 mock 做桩
        HttpResponse<Void> response = statusResponse(statusCode);
        when(client.send(any(HttpRequest.class), anyHandler())).thenReturn(response);
    }

    /**
     * 包装 {@code BodyHandlers.discarding()} 的匹配器，显式固定泛型为 {@code Void}。
     */
    private static HttpResponse.BodyHandler<Void> anyHandler() {
        return any();
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse<Void> statusResponse(int statusCode) {
        HttpResponse<Void> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(statusCode);
        return response;
    }

    /**
     * 读取 {@code BodyPublishers.ofString} 的实际内容，用于断言请求体字段。
     */
    private static String requestBody(HttpRequest request) throws Exception {
        HttpRequest.BodyPublisher publisher = request.bodyPublisher().orElseThrow();
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        CountDownLatch latch = new CountDownLatch(1);
        publisher.subscribe(new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                subscription.request(Long.MAX_VALUE);
            }

            @Override
            public void onNext(ByteBuffer item) {
                byte[] bytes = new byte[item.remaining()];
                item.get(bytes);
                buffer.writeBytes(bytes);
            }

            @Override
            public void onError(Throwable throwable) {
                latch.countDown();
            }

            @Override
            public void onComplete() {
                latch.countDown();
            }
        });
        assertThat(latch.await(5, TimeUnit.SECONDS)).isTrue();
        return buffer.toString(StandardCharsets.UTF_8);
    }
}
