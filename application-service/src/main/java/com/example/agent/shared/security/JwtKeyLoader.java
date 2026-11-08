package com.example.agent.shared.security;

import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

/**
 * PEM 密钥解析工具。
 *
 * <p>环境变量注入的多行 PEM 在不同 shell 与编排工具里会被压成一行，因此这里同时
 * 接受真实换行与字面量 {@code \n}，并容忍值被引号包裹。只支持 PKCS#8 私钥与
 * X.509 公钥两种格式，其他格式一律视为配置错误。</p>
 */
public final class JwtKeyLoader {

    private static final String ESCAPED_NEWLINE = "\\n";

    private static final String PRIVATE_KEY_TYPE = "PRIVATE KEY";

    private static final String PUBLIC_KEY_TYPE = "PUBLIC KEY";

    private JwtKeyLoader() {
    }

    /**
     * 解析 PKCS#8 PEM 私钥。
     *
     * @param pem PEM 文本，允许 {@code \n} 转义
     * @return RSA 私钥
     * @throws IllegalArgumentException 格式不合法时抛出
     */
    public static RSAPrivateKey loadPrivateKey(String pem) {
        try {
            byte[] der = decode(pem, PRIVATE_KEY_TYPE);
            return (RSAPrivateKey) KeyFactory.getInstance("RSA")
                    .generatePrivate(new PKCS8EncodedKeySpec(der));
        } catch (GeneralSecurityException | ClassCastException ex) {
            throw new IllegalArgumentException("JWT 私钥解析失败，需要 PKCS#8 PEM（-----BEGIN PRIVATE KEY-----）", ex);
        }
    }

    /**
     * 解析 X.509 PEM 公钥。
     *
     * @param pem PEM 文本，允许 {@code \n} 转义
     * @return RSA 公钥
     * @throws IllegalArgumentException 格式不合法时抛出
     */
    public static RSAPublicKey loadPublicKey(String pem) {
        try {
            byte[] der = decode(pem, PUBLIC_KEY_TYPE);
            return (RSAPublicKey) KeyFactory.getInstance("RSA")
                    .generatePublic(new X509EncodedKeySpec(der));
        } catch (GeneralSecurityException | ClassCastException ex) {
            throw new IllegalArgumentException("JWT 公钥解析失败，需要 X.509 PEM（-----BEGIN PUBLIC KEY-----）", ex);
        }
    }

    /**
     * 归一化 PEM 文本：去首尾空白与包裹引号，把字面量 {@code \n} 还原为换行。
     *
     * @param pem 原始配置值
     * @return 可解析的 PEM 文本
     */
    public static String normalize(String pem) {
        if (pem == null) {
            throw new IllegalArgumentException("PEM 内容为空");
        }
        String value = pem.trim();
        if (value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
            value = value.substring(1, value.length() - 1);
        }
        return value.replace(ESCAPED_NEWLINE, "\n").replace("\r", "");
    }

    private static byte[] decode(String pem, String type) {
        String value = normalize(pem);
        String beginMarker = "-----BEGIN " + type + "-----";
        String endMarker = "-----END " + type + "-----";
        int beginIndex = value.indexOf(beginMarker);
        int endIndex = value.indexOf(endMarker);
        if (beginIndex < 0 || endIndex <= beginIndex) {
            throw new IllegalArgumentException("PEM 缺少 " + beginMarker + " 或 " + endMarker);
        }
        String body = value.substring(beginIndex + beginMarker.length(), endIndex);
        return Base64.getMimeDecoder().decode(body);
    }
}
