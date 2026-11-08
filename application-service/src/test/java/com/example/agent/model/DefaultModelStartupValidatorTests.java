package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.model.application.DefaultModelStartupValidator;
import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

/**
 * 默认模型启动校验：运行时关闭时跳过；引用不可用时必须阻断启动。
 */
class DefaultModelStartupValidatorTests {

    private static final String DEFAULT_KEY = "deepseek:deepseek-v4-pro";

    private final ModelRuntimeProperties properties = new ModelRuntimeProperties();
    private final CredentialKeyRing credentialKeyRing = new CredentialKeyRing(properties);
    private final ModelCatalogService modelCatalogService = mock(ModelCatalogService.class);
    private final DefaultModelStartupValidator validator =
            new DefaultModelStartupValidator(properties, credentialKeyRing, modelCatalogService);

    private static DefaultApplicationArguments noArguments() {
        return new DefaultApplicationArguments(new String[0]);
    }

    @Test
    void run_shouldSkipCatalogLookup_whenRuntimeDisabled() {
        properties.setRuntimeEnabled(false);

        assertThatCode(() -> validator.run(noArguments())).doesNotThrowAnyException();
        verify(modelCatalogService, never()).requireAvailable(anyString());
    }

    @Test
    void run_shouldFailFast_whenDefaultModelIsNotAvailable() {
        properties.setRuntimeEnabled(true);
        properties.setDefaultModelKey(DEFAULT_KEY);
        when(modelCatalogService.requireAvailable(DEFAULT_KEY))
                .thenThrow(new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE));

        assertThatThrownBy(() -> validator.run(noArguments()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(DEFAULT_KEY);
    }

    @Test
    void run_shouldPass_whenDefaultModelIsResolvable() {
        properties.setRuntimeEnabled(true);
        properties.setDefaultModelKey(DEFAULT_KEY);
        when(modelCatalogService.requireAvailable(DEFAULT_KEY))
                .thenReturn(new ResolvedModel("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro",
                        List.of("text", "tool_calling"), null));

        assertThatCode(() -> validator.run(noArguments())).doesNotThrowAnyException();
    }
}
