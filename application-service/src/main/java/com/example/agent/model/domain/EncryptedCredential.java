package com.example.agent.model.domain;

import java.util.UUID;

/**
 * 已加密的凭证快照。
 *
 * <p>只承载密文与展示所需的掩码，明文解密仍由 application 层的 cipher 完成，
 * 保证密钥材料不进入 infrastructure。</p>
 *
 * @param id             凭证标识
 * @param connectionId   所属连接
 * @param userPublicId   所属用户
 * @param credentialType 凭证类型
 * @param ciphertext     密文
 * @param keyVersion     加密密钥版本
 * @param maskedHint     展示用掩码
 * @param status         凭证状态
 */
public record EncryptedCredential(
        UUID id,
        UUID connectionId,
        UUID userPublicId,
        String credentialType,
        String ciphertext,
        int keyVersion,
        String maskedHint,
        String status) {
}
