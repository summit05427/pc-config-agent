package com.example.agent.model.domain;

import com.example.agent.shared.error.BusinessException;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/**
 * 接入地址校验策略。
 *
 * <p>连接创建与出站探测共用同一套规则：只允许 HTTP(S)，拒绝回环、链路本地与私网字面量地址。
 * 真正发起请求前还会再校验一次，防止数据库中的旧值绕过创建时的校验。</p>
 */
public final class BaseUrlPolicy {

    private static final String SCHEME_HTTP = "http";

    private static final String SCHEME_HTTPS = "https";

    private BaseUrlPolicy() {
    }

    /**
     * 校验并归一化接入地址（去掉尾部斜杠）。
     *
     * @param candidate 原始地址
     * @return 归一化后的地址
     * @throws BusinessException 协议非法、主机缺失或命中禁止网段时抛出 {@link ModelErrorCode#BASE_URL_INVALID}
     */
    public static String normalize(String candidate) {
        String value = candidate == null ? "" : candidate.trim();
        if (value.isEmpty()) {
            throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
        }
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            if (!SCHEME_HTTPS.equals(scheme) && !SCHEME_HTTP.equals(scheme)) {
                throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
            }
            String host = uri.getHost();
            if (host == null || host.isBlank() || isForbiddenHost(host)) {
                throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
            }
        } catch (URISyntaxException ex) {
            throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
        }
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    /**
     * 拒绝回环、私网、链路本地与保留网段（DNS 解析后的实际地址）。
     *
     * <p>仅校验字面量不足以防止「公网域名解析到内网 IP」的 SSRF；出站前必须对
     * DNS 结果逐个检查。DNS rebinding 的 TOCTOU 窗口仍需出站客户端禁用重定向，
     * 并在网络层限制服务可访问网段。</p>
     *
     * @param address DNS 解析得到的地址
     * @return 命中禁止网段时为 {@code true}
     */
    public static boolean isForbiddenAddress(InetAddress address) {
        if (address == null) {
            return true;
        }
        if (address.isAnyLocalAddress()
                || address.isLoopbackAddress()
                || address.isLinkLocalAddress()
                || address.isSiteLocalAddress()
                || address.isMulticastAddress()) {
            return true;
        }
        if (address instanceof Inet4Address) {
            byte[] bytes = address.getAddress();
            return isPrivateIpv4Bytes(bytes);
        }
        if (address instanceof Inet6Address) {
            byte[] bytes = address.getAddress();
            // fc00::/7 唯一本地地址
            if ((bytes[0] & 0xFE) == 0xFC) {
                return true;
            }
            // IPv4-mapped IPv6（::ffff:a.b.c.d）可能绕过 IPv4 检查，按其内嵌地址判断
            if (isIpv4Mapped(bytes)) {
                return isPrivateIpv4Bytes(new byte[] {
                        bytes[12], bytes[13], bytes[14], bytes[15]});
            }
        }
        return false;
    }

    private static boolean isIpv4Mapped(byte[] bytes) {
        for (int index = 0; index < 10; index++) {
            if (bytes[index] != 0) {
                return false;
            }
        }
        return (bytes[10] & 0xFF) == 0xFF && (bytes[11] & 0xFF) == 0xFF;
    }

    private static boolean isPrivateIpv4Bytes(byte[] bytes) {
        int first = bytes[0] & 0xFF;
        int second = bytes[1] & 0xFF;
        return first == 0 || first == 10 || first == 127
                || (first == 100 && second >= 64 && second <= 127)
                || (first == 169 && second == 254)
                || (first == 172 && second >= 16 && second <= 31)
                || (first == 192 && second == 168)
                || (first == 198 && (second == 18 || second == 19));
    }

    /**
     * 拒绝回环与私网字面量地址。
     *
     * <p>放开等于把服务端当成用户可用的 SSRF 跳板。DNS 重绑定无法在这里拦截，
     * 出站客户端需禁用自动重定向并在调用前再次校验。</p>
     *
     * @param host 主机名或 IP 字面量
     * @return 命中禁止网段时为 {@code true}
     */
    public static boolean isForbiddenHost(String host) {
        String normalized = host.toLowerCase(Locale.ROOT);
        if (normalized.startsWith("[") && normalized.endsWith("]")) {
            normalized = normalized.substring(1, normalized.length() - 1);
        }
        if ("localhost".equals(normalized) || normalized.endsWith(".localhost")) {
            return true;
        }
        if (normalized.contains(":")) {
            // IPv6 字面量：回环、链路本地与唯一本地地址段
            return "::1".equals(normalized) || "::".equals(normalized)
                    || normalized.startsWith("fe80:") || normalized.startsWith("fc")
                    || normalized.startsWith("fd");
        }
        return isPrivateIpv4(normalized);
    }

    private static boolean isPrivateIpv4(String host) {
        String[] segments = host.split("\\.");
        if (segments.length != 4) {
            return false;
        }
        try {
            int first = Integer.parseInt(segments[0]);
            int second = Integer.parseInt(segments[1]);
            return first == 0 || first == 10 || first == 127
                    || (first == 169 && second == 254)
                    || (first == 172 && second >= 16 && second <= 31)
                    || (first == 192 && second == 168);
        } catch (NumberFormatException ex) {
            return false;
        }
    }
}
