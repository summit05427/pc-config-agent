package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.shared.config.ModelRuntimeProperties;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class CredentialKeyRingTests {

    private static final String KEY_V1 = base64Key("0123456789abcdef0123456789abcdef");
    private static final String KEY_V2 = base64Key("abcdef0123456789abcdef0123456789");

    @Test
    void shouldResolveEveryVersion_whenKeyRingIsValid() {
        CredentialKeyRing keyRing = new CredentialKeyRing(propertiesWithKeyRing("1:" + KEY_V1 + ",2:" + KEY_V2, 2));

        assertThat(keyRing.keyForVersion(1)).isEqualTo(KEY_V1);
        assertThat(keyRing.keyForVersion(2)).isEqualTo(KEY_V2);
        assertThat(keyRing.currentVersion()).isEqualTo(2);
        assertThat(keyRing.isCurrentVersionUsable()).isTrue();
    }

    @Test
    void shouldFailFast_whenKeyRingEntryIsMalformed() {
        // 配置了密钥环但内容非法时不允许回退单密钥，否则轮换期可能误用旧密钥
        assertThatThrownBy(() -> new CredentialKeyRing(propertiesWithKeyRing("2:not-a-base64-key", 1)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("key-ring");
    }

    @Test
    void shouldFailFast_whenKeyRingMissesCurrentVersion() {
        assertThatThrownBy(() -> new CredentialKeyRing(propertiesWithKeyRing("1:" + KEY_V1, 2)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("key-version");
    }

    @Test
    void shouldFallBackToSingleKey_whenKeyRingIsBlank() {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setMasterKey(KEY_V1);
        properties.getCredential().setKeyVersion(1);

        CredentialKeyRing keyRing = new CredentialKeyRing(properties);

        assertThat(keyRing.keyForVersion(1)).isEqualTo(KEY_V1);
        assertThat(keyRing.keyForVersion(2)).isNull();
        assertThat(keyRing.isCurrentVersionUsable()).isTrue();
    }

    @Test
    void shouldReportUnusable_whenSingleKeyIsInvalid() {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setMasterKey("too-short");
        properties.getCredential().setKeyVersion(1);

        CredentialKeyRing keyRing = new CredentialKeyRing(properties);

        assertThat(keyRing.isCurrentVersionUsable()).isFalse();
    }

    private static ModelRuntimeProperties propertiesWithKeyRing(String keyRing, int keyVersion) {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setKeyRing(keyRing);
        properties.getCredential().setKeyVersion(keyVersion);
        return properties;
    }

    private static String base64Key(String seed) {
        byte[] bytes = seed.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
