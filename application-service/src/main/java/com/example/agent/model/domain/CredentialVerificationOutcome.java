package com.example.agent.model.domain;

/**
 * 一次凭证验证的分类结果。
 *
 * <p>结果是验证模块对外 interface 的一部分：调用方按结果决定提示与错误码，
 * 不再各自解析探测组件的内部枚举。</p>
 */
public enum CredentialVerificationOutcome {

    /** 上游接受凭证，连接与凭证状态已回写。 */
    VERIFIED,

    /** 上游明确拒绝凭证（401/403），凭证状态已回写为 INVALID。 */
    REJECTED,

    /** 上游不可达、超时或返回非预期状态，状态未改变。 */
    UNAVAILABLE,

    /** 本地密文无法解密或与掩码不一致，状态未改变。 */
    CORRUPTED
}
