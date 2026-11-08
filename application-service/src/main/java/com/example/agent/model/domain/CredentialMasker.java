package com.example.agent.model.domain;

/**
 * 凭证掩码工具。
 *
 * <p>掩码只用于展示，不能被当作校验依据：它能证明「后端曾见过明文」，
 * 但不能证明明文正确。真正校验必须解密后重新计算并与库中掩码比对。</p>
 */
public final class CredentialMasker {

    private static final int VISIBLE_PREFIX = 3;
    private static final int VISIBLE_SUFFIX = 4;
    private static final int MIN_MASKABLE_LENGTH = VISIBLE_PREFIX + VISIBLE_SUFFIX + 1;
    private static final String HIDDEN = "****";
    private static final String FULLY_HIDDEN = HIDDEN;

    private CredentialMasker() {
    }

    /**
     * 生成掩码，如 {@code sk-****abcd}。
     *
     * @param secret 明文密钥
     * @return 长度不足以展示前后缀时返回 {@code ****}
     * @throws IllegalArgumentException 明文为空时抛出，空密钥不应进入任何链路
     */
    public static String mask(String secret) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalArgumentException("凭证不能为空");
        }
        String trimmed = secret.trim();
        if (trimmed.length() < MIN_MASKABLE_LENGTH) {
            return FULLY_HIDDEN;
        }
        return trimmed.substring(0, VISIBLE_PREFIX)
                + HIDDEN
                + trimmed.substring(trimmed.length() - VISIBLE_SUFFIX);
    }
}
