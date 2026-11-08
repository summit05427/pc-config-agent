package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.model.domain.CredentialMasker;
import org.junit.jupiter.api.Test;

/**
 * 掩码规则单测：只暴露固定前后缀，短密钥不泄露任何字符。
 */
class CredentialMaskerTests {

    @Test
    void mask_shouldKeepPrefixAndSuffixForLongSecret() {
        assertThat(CredentialMasker.mask("sk-1234567890")).isEqualTo("sk-****7890");
    }

    @Test
    void mask_shouldHideEverythingForShortSecret() {
        assertThat(CredentialMasker.mask("abc1234")).isEqualTo("****");
    }

    @Test
    void mask_shouldTrimSurroundingWhitespace() {
        assertThat(CredentialMasker.mask("  sk-1234567890  ")).isEqualTo("sk-****7890");
    }

    @Test
    void mask_shouldRejectBlankSecret() {
        assertThatThrownBy(() -> CredentialMasker.mask(" ")).isInstanceOf(IllegalArgumentException.class);
    }
}
