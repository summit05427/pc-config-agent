package com.example.agent.model.web.dto;

import com.example.agent.model.domain.CredentialLease;

/**
 * 凭证兑换响应：只在本响应中出现一次明文，Agent 必须随任务结束丢弃。
 *
 * @param credentialType 凭证类型
 * @param secret         明文凭证
 * @param expiresIn      有效期（秒）
 */
public record CredentialLeaseResponse(String credentialType, String secret, long expiresIn) {

    /**
     * @param lease 服务层兑换结果
     * @return 对外响应对象
     */
    public static CredentialLeaseResponse from(CredentialLease lease) {
        return new CredentialLeaseResponse(lease.credentialType(), lease.secret(), lease.expiresIn());
    }
}
