package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * Provider 凭证加解密（AES-256-GCM）。
 *
 * <p>每次加密生成独立 12 字节 nonce 与 16 字节认证标签，密文结构固定为
 * {@code v1:<key_version>:<base64(nonce|tag|ciphertext)>}。认证标签使任何篡改
 * （包括换明文、换 nonce、截断密文）在解密时立即失败，不需要额外校验列。</p>
 *
 * <p>主密钥只来自环境变量，不在本类中缓存明文；失败信息统一为
 * {@link ModelErrorCode#CREDENTIAL_CORRUPTED}，不携带密钥、nonce 或底层异常消息。</p>
 */
@Component
@RequiredArgsConstructor
public class ProviderCredentialCipher {

    private static final String FORMAT_VERSION = "v1";

    private static final String TRANSFORMATION = "AES/GCM/NoPadding";

    private static final int NONCE_BYTES = 12;

    private static final int TAG_BITS = 128;

    private static final int TAG_BYTES = TAG_BITS / Byte.SIZE;

    private static final int MIN_PAYLOAD_BYTES = NONCE_BYTES + TAG_BYTES;

    private static final int FORMAT_PARTS = 3;

    private static final String FORMAT_SEPARATOR = ":";

    private final CredentialKeyRing keyRing;

    private final SecureRandom secureRandom = new SecureRandom();

    /**
     * 加密明文并返回可入库的密文串。
     *
     * @param plaintext 明文密钥
     * @return {@code v1:<key_version>:<base64>} 密文
     */
    public String encrypt(String plaintext) {
        if (plaintext == null || plaintext.isBlank()) {
            throw new IllegalArgumentException("凭证不能为空");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE,
                    masterKey(keyRing.currentVersion()),
                    new GCMParameterSpec(TAG_BITS, nonce));
            byte[] encrypted = cipher.doFinal(plaintext.trim().getBytes(StandardCharsets.UTF_8));
            return FORMAT_VERSION
                    + FORMAT_SEPARATOR
                    + keyRing.currentVersion()
                    + FORMAT_SEPARATOR
                    + Base64.getEncoder().encodeToString(concat(nonce, encrypted));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("凭证加密失败", ex);
        }
    }

    /**
     * 解密并返回明文密钥；调用方必须在最小作用域内使用并及时丢弃。
     *
     * <p>按密文中记录的 {@code key_version} 选择主密钥，支持密钥轮换后继续读取旧密文。</p>
     *
     * @param ciphertext 入库密文
     * @return 明文密钥
     * @throws BusinessException 格式非法、版本未配置或认证标签校验失败时抛出 500
     */
    public String decrypt(String ciphertext) {
        DecodedCiphertext decoded = decodePayload(ciphertext);
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, masterKey(decoded.keyVersion()),
                    new GCMParameterSpec(TAG_BITS, decoded.payload(), 0, NONCE_BYTES));
            byte[] plaintext = cipher.doFinal(
                    decoded.payload(), NONCE_BYTES, decoded.payload().length - NONCE_BYTES);
            return new String(plaintext, StandardCharsets.UTF_8);
        } catch (GeneralSecurityException ex) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
    }

    private DecodedCiphertext decodePayload(String ciphertext) {
        if (ciphertext == null || ciphertext.isBlank()) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
        String[] parts = ciphertext.split(FORMAT_SEPARATOR, FORMAT_PARTS);
        if (parts.length != FORMAT_PARTS || !FORMAT_VERSION.equals(parts[0])) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
        try {
            int keyVersion = Integer.parseInt(parts[1]);
            if (keyVersion < 1) {
                throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
            }
            byte[] payload = Base64.getDecoder().decode(parts[2]);
            if (payload.length < MIN_PAYLOAD_BYTES) {
                throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
            }
            return new DecodedCiphertext(keyVersion, payload);
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
    }

    private SecretKeySpec masterKey(int keyVersion) {
        String encodedKey = keyRing.keyForVersion(keyVersion);
        if (encodedKey == null) {
            // 版本未配置属于部署问题，但对调用方统一表现为密文不可用，避免泄露密钥配置细节
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
        return new SecretKeySpec(Base64.getDecoder().decode(encodedKey), "AES");
    }

    private record DecodedCiphertext(int keyVersion, byte[] payload) {
    }

    private static byte[] concat(byte[] first, byte[] second) {
        byte[] result = new byte[first.length + second.length];
        System.arraycopy(first, 0, result, 0, first.length);
        System.arraycopy(second, 0, result, first.length, second.length);
        return result;
    }
}
