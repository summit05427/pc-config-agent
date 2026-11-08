package com.example.agent.identity.domain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

/**
 * Refresh Token 的生成与摘要工具。
 *
 * <p>令牌是 256 bit 随机不透明串（Base64URL 编码，43 个字符），不含任何身份信息；
 * 数据库只保存它的 SHA-256 摘要，即使库被读走也无法还原出可用令牌。</p>
 */
public final class RefreshTokens {

    /** 256 bit 熵：远高于暴力猜测所需，同时保持 Cookie 体积可控。 */
    private static final int TOKEN_BYTES = 32;

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private static final Base64.Encoder URL_ENCODER = Base64.getUrlEncoder().withoutPadding();

    private static final String HASH_ALGORITHM = "SHA-256";

    private RefreshTokens() {
    }

    /**
     * 生成新的 Refresh Token 明文。
     *
     * @return Base64URL 编码的随机令牌，只返回给客户端一次
     */
    public static String generate() {
        byte[] bytes = new byte[TOKEN_BYTES];
        SECURE_RANDOM.nextBytes(bytes);
        return URL_ENCODER.encodeToString(bytes);
    }

    /**
     * 计算令牌摘要。
     *
     * <p>摘要不可逆，且数据库列长度固定 64 位十六进制，便于唯一约束与索引查找。</p>
     *
     * @param rawToken 客户端出示的令牌明文
     * @return 小写十六进制 SHA-256 摘要
     */
    public static String hash(String rawToken) {
        try {
            // MessageDigest 非线程安全，每次新建实例，避免并发下摘要错乱
            MessageDigest digest = MessageDigest.getInstance(HASH_ALGORITHM);
            return HexFormat.of().formatHex(digest.digest(rawToken.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            // SHA-256 是 JDK 必备算法，走到这里说明运行环境被破坏
            throw new IllegalStateException("当前 JDK 不支持 SHA-256", ex);
        }
    }
}
