package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.HostResolver;
import com.example.agent.model.infrastructure.OutboundHostGuard;
import com.example.agent.shared.error.BusinessException;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * 出站地址守卫单测：字面量与 DNS 解析结果都必须过滤，且任何一条命中即拒绝。
 *
 * <p>用固定 {@link HostResolver} 注入解析结果，既不依赖真实 DNS，也能精确覆盖
 * 「公网域名解析到私网 IP」这类只看字面量会漏掉的 SSRF 场景。</p>
 */
class OutboundHostGuardTests {

    private static final String PUBLIC_URL = "https://api.example.com/v1";

    @Test
    void validate_shouldReturnNormalizedUrl_whenAllAddressesArePublic() throws Exception {
        OutboundHostGuard guard = guardReturning(InetAddress.getByName("8.8.8.8"));

        assertThat(guard.validate(PUBLIC_URL + "/")).isEqualTo(PUBLIC_URL);
    }

    @Test
    void validate_shouldRejectDomainResolvingToPrivateAddress() throws Exception {
        OutboundHostGuard guard = guardReturning(InetAddress.getByName("10.0.0.5"));

        assertThatThrownBy(() -> guard.validate(PUBLIC_URL))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldReject_whenAnyResolvedAddressIsForbidden() throws Exception {
        // 多 A 记录时只要有一条指向内网就必须整体拒绝
        OutboundHostGuard guard = guardReturning(
                InetAddress.getByName("1.1.1.1"), InetAddress.getByName("192.168.1.10"));

        assertThatThrownBy(() -> guard.validate(PUBLIC_URL))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldRejectIpv4MappedPrivateIpv6() throws Exception {
        OutboundHostGuard guard = guardReturning(InetAddress.getByName("::ffff:127.0.0.1"));

        assertThatThrownBy(() -> guard.validate(PUBLIC_URL))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldRejectIpv6UniqueLocalAddress() throws Exception {
        OutboundHostGuard guard = guardReturning(InetAddress.getByName("fc00::1"));

        assertThatThrownBy(() -> guard.validate(PUBLIC_URL))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldRejectPrivateOrLoopbackLiteralBeforeResolving() {
        HostResolver neverCalled = host -> {
            throw new AssertionError("字面量地址不应进入 DNS 解析");
        };
        OutboundHostGuard guard = new OutboundHostGuard(neverCalled);

        assertThatThrownBy(() -> guard.validate("http://127.0.0.1/v1"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        assertThatThrownBy(() -> guard.validate("http://localhost:11434/v1"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        assertThatThrownBy(() -> guard.validate("http://[::1]/v1"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldReject_whenHostCannotBeResolved() {
        OutboundHostGuard guard = new OutboundHostGuard(host -> {
            throw new UnknownHostException(host);
        });

        assertThatThrownBy(() -> guard.validate(PUBLIC_URL))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    @Test
    void validate_shouldRejectUnsupportedSchemeAndEmptyHost() {
        OutboundHostGuard guard = guardReturning();

        assertThatThrownBy(() -> guard.validate("ftp://example.com"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        assertThatThrownBy(() -> guard.validate("https://"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
    }

    private static OutboundHostGuard guardReturning(InetAddress... addresses) {
        List<InetAddress> resolved = Arrays.asList(addresses);
        return new OutboundHostGuard(host -> resolved);
    }
}
