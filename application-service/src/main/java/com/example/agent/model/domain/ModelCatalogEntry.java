package com.example.agent.model.domain;

/**
 * 面向用户的模型目录条目：模型本身 + 本次使用的凭证来源。
 *
 * <p>凭证来源与运行时解析规则保持一致：该 Provider 存在可用 BYOK 连接时为
 * {@link #SOURCE_BYOK}，否则为平台托管的 {@link #SOURCE_MANAGED}。前端据此
 * 区分「平台提供」与「我的密钥」，不需要自行推断。</p>
 *
 * @param model            解析后的模型
 * @param credentialSource 凭证来源：{@code MANAGED} 或 {@code BYOK}
 */
public record ModelCatalogEntry(ResolvedModel model, String credentialSource) {

    /** 平台托管凭证。 */
    public static final String SOURCE_MANAGED = "MANAGED";

    /** 用户自带凭证。 */
    public static final String SOURCE_BYOK = "BYOK";
}
