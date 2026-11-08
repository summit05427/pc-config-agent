package com.example.agent.model.infrastructure;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;

/**
 * 主机名解析抽象：生产使用 DNS，测试可注入固定结果。
 *
 * <p>出站 SSRF 防护必须在解析之后检查实际 IP，否则「公网域名指向内网」
 * 仍然可以绕过只看字面量的校验。</p>
 */
@FunctionalInterface
public interface HostResolver {

    /**
     * @param host 主机名或 IP 字面量
     * @return 解析到的全部地址
     * @throws UnknownHostException 无法解析时抛出
     */
    List<InetAddress> resolve(String host) throws UnknownHostException;
}
