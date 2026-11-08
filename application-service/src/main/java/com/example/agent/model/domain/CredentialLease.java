package com.example.agent.model.domain;

/**
 * 一次性的凭证兑换结果。
 *
 * <p>明文密钥只存在于该对象的生命周期内；覆盖 {@code toString} 防止日志或调试输出
 * 误把密钥写进日志。</p>
 *
 * @param credentialType 凭证类型，首版固定 {@code api_key}
 * @param secret         明文凭证
 * @param expiresIn      有效期（秒），取任务剩余时长
 */
public record CredentialLease(String credentialType, String secret, long expiresIn) {

    @Override
    public String toString() {
        return "CredentialLease[credentialType=" + credentialType
                + ", secret=***, expiresIn=" + expiresIn + "]";
    }
}
