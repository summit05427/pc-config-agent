package com.example.agent.shared.web;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

/**
 * 客户端 IP 解析优先级与长度保护。
 */
class ClientIpResolverTests {

    @Test
    void resolve_prefersFirstForwardedForSegment() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("127.0.0.1");
        request.addHeader("X-Forwarded-For", "203.0.113.7, 10.0.0.1, 10.0.0.2");

        assertThat(ClientIpResolver.resolve(request)).isEqualTo("203.0.113.7");
    }

    @Test
    void resolve_fallsBackToRealIpThenRemoteAddress() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("127.0.0.1");
        request.addHeader("X-Real-IP", "198.51.100.9");

        assertThat(ClientIpResolver.resolve(request)).isEqualTo("198.51.100.9");

        request.removeHeader("X-Real-IP");
        assertThat(ClientIpResolver.resolve(request)).isEqualTo("127.0.0.1");
    }

    @Test
    void resolve_rejectsOverlongHeader() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Forwarded-For", "x".repeat(46));

        assertThat(ClientIpResolver.resolve(request)).isNull();
    }

    @Test
    void resolve_handlesBlankHeader() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("127.0.0.1");
        request.addHeader("X-Forwarded-For", "  ");

        assertThat(ClientIpResolver.resolve(request)).isEqualTo("127.0.0.1");
    }
}
