package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.BaseUrlPolicy;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 出站地址守卫：语法校验 + DNS 解析后逐地址检查。
 *
 * <p>创建连接和真正发请求前都必须经过这里；只校验字面量会漏掉
 * 「公网域名解析到 127.0.0.1 / 10.x.x.x」的 SSRF。DNS rebinding 仍存在
 * 校验与请求之间的时间窗，因此出站客户端必须禁用重定向，部署侧也应限制
 * 服务可访问的网段。</p>
 */
@Component
@RequiredArgsConstructor
public class OutboundHostGuard {

    private final HostResolver hostResolver;

    /**
     * 校验并归一化接入地址。
     *
     * @param candidate 用户输入或配置中的地址
     * @return 去掉尾部斜杠的地址
     * @throws BusinessException 协议非法、主机缺失、无法解析或命中禁止网段时 400
     */
    public String validate(String candidate) {
        String normalized = BaseUrlPolicy.normalize(candidate);
        String host = URI.create(normalized).getHost();
        if (host == null || host.isBlank()) {
            throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
        }
        String bareHost = stripBrackets(host).toLowerCase(Locale.ROOT);
        List<InetAddress> addresses;
        try {
            addresses = hostResolver.resolve(bareHost);
        } catch (UnknownHostException | SecurityException ex) {
            // 解析失败时不区分「域名不存在」与「被安全策略拒绝」，避免成为探测口
            throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
        }
        if (addresses.isEmpty() || addresses.stream().anyMatch(BaseUrlPolicy::isForbiddenAddress)) {
            throw new BusinessException(ModelErrorCode.BASE_URL_INVALID);
        }
        return normalized;
    }

    private static String stripBrackets(String host) {
        if (host.startsWith("[") && host.endsWith("]")) {
            return host.substring(1, host.length() - 1);
        }
        return host;
    }
}
