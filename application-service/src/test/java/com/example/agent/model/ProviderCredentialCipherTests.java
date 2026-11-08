package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.model.application.ProviderCredentialCipher;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 凭证加解密单测：每次加密独立 nonce，任何篡改或格式异常都必须在解密阶段失败。
 */
class ProviderCredentialCipherTests {

    private static final String MASTER_KEY = Base64.getEncoder()
            .encodeToString("0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8));

    private static final String OTHER_MASTER_KEY = Base64.getEncoder()
            .encodeToString("abcdef0123456789abcdef0123456789".getBytes(StandardCharsets.UTF_8));

    private static final String SECRET = "sk-test-1234567890";

    private static final String PREFIX = "v1:1:";

    private ProviderCredentialCipher cipher;

    @BeforeEach
    void setUp() {
        cipher = cipherWith(propertiesWithKey(MASTER_KEY));
    }

    @Test
    void encrypt_shouldProduceUniqueCiphertextAndRoundTrip() {
        String first = cipher.encrypt(SECRET);
        String second = cipher.encrypt(SECRET);

        assertThat(first).startsWith(PREFIX);
        // 同一明文两次加密必须不同：nonce 复用会让 GCM 失去语义安全
        assertThat(first).isNotEqualTo(second);
        assertThat(cipher.decrypt(first)).isEqualTo(SECRET);
        assertThat(cipher.decrypt(second)).isEqualTo(SECRET);
    }

    @Test
    void decrypt_shouldFail_whenCiphertextIsTampered() {
        byte[] payload = payloadOf(cipher.encrypt(SECRET));
        payload[payload.length - 1] ^= 0x01;
        String tampered = PREFIX + Base64.getEncoder().encodeToString(payload);

        assertThatThrownBy(() -> cipher.decrypt(tampered))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_CORRUPTED));
    }

    @Test
    void decrypt_shouldFail_whenMasterKeyDiffers() {
        String encrypted = cipher.encrypt(SECRET);
        ProviderCredentialCipher other = cipherWith(propertiesWithKey(OTHER_MASTER_KEY));

        assertThatThrownBy(() -> other.decrypt(encrypted))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_CORRUPTED));
    }

    @Test
    void decrypt_shouldReadLegacyCiphertext_whenKeyRingContainsOldVersion() {
        String legacy = cipher.encrypt(SECRET);
        ProviderCredentialCipher rotated = cipherWith(
                propertiesWithKeyRing("1:" + MASTER_KEY + ",2:" + OTHER_MASTER_KEY, 2));

        // 轮换后新密文用版本 2，旧密文仍能按自带的版本 1 解密
        assertThat(rotated.decrypt(legacy)).isEqualTo(SECRET);
        assertThat(rotated.encrypt(SECRET)).startsWith("v1:2:");
        assertThat(rotated.decrypt(rotated.encrypt(SECRET))).isEqualTo(SECRET);
    }

    @Test
    void decrypt_shouldFail_whenKeyRingMissesCiphertextVersion() {
        String legacy = cipher.encrypt(SECRET);
        ProviderCredentialCipher rotated = cipherWith(
                propertiesWithKeyRing("2:" + OTHER_MASTER_KEY, 2));

        assertCorrupted(rotated, legacy);
    }

    @Test
    void decrypt_shouldFail_whenFormatIsInvalid() {
        assertCorrupted(null);
        assertCorrupted("   ");
        assertCorrupted("plain-secret");
        assertCorrupted("v2:1:AAAA");
        assertCorrupted("v1:0:AAAA");
        // 载荷不足 nonce + tag 长度，说明密文被截断
        assertCorrupted("v1:1:AAAA");
    }

    @Test
    void encrypt_shouldRejectBlankPlaintext() {
        assertThatThrownBy(() -> cipher.encrypt("   ")).isInstanceOf(IllegalArgumentException.class);
    }

    private void assertCorrupted(String ciphertext) {
        assertCorrupted(cipher, ciphertext);
    }

    private static void assertCorrupted(ProviderCredentialCipher target, String ciphertext) {
        assertThatThrownBy(() -> target.decrypt(ciphertext))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_CORRUPTED));
    }

    private static byte[] payloadOf(String ciphertext) {
        return Base64.getDecoder().decode(ciphertext.substring(PREFIX.length()));
    }

    private static ModelRuntimeProperties propertiesWithKey(String masterKey) {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setMasterKey(masterKey);
        properties.getCredential().setKeyVersion(1);
        return properties;
    }

    private static ProviderCredentialCipher cipherWith(ModelRuntimeProperties properties) {
        return new ProviderCredentialCipher(new CredentialKeyRing(properties));
    }

    private static ModelRuntimeProperties propertiesWithKeyRing(String keyRing, int keyVersion) {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setKeyRing(keyRing);
        properties.getCredential().setKeyVersion(keyVersion);
        return properties;
    }
}
