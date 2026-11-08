package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.UserPreferenceDirectory;
import com.example.agent.identity.application.UserPreferenceService;
import com.example.agent.identity.domain.ReplyLanguage;
import com.example.agent.identity.domain.ResponseStyle;
import com.example.agent.identity.domain.UserPreference;
import com.example.agent.identity.web.dto.UserPreferenceResponse;
import com.example.agent.identity.web.dto.UserPreferenceUpdateRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 用户偏好服务单测：不启动 Spring 容器，存储通过 Mockito 隔离。
 *
 * <p>参数校验在 API 层由 Bean Validation 完成，这里覆盖「内部调用绕过校验」时的兜底分支。</p>
 */
@ExtendWith(MockitoExtension.class)
class UserPreferenceServiceTests {

    private static final String PUBLIC_ID = "9d1a7f6e-2b3c-4d5e-8f90-1a2b3c4d5e6f";
    private static final Instant UPDATED_AT = Instant.parse("2026-10-29T09:00:00Z");

    @Mock
    private UserPreferenceDirectory userPreferenceDirectory;

    @InjectMocks
    private UserPreferenceService userPreferenceService;

    @Test
    void getPreferences_shouldReturnDefaults_whenNothingSaved() {
        when(userPreferenceDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.empty());

        UserPreferenceResponse response = userPreferenceService.getPreferences(PUBLIC_ID);

        assertThat(response.instructions()).isNull();
        assertThat(response.replyLanguage()).isEqualTo("auto");
        assertThat(response.responseStyle()).isEqualTo("balanced");
        assertThat(response.useHistory()).isTrue();
        // 从未保存过时不伪造保存时间
        assertThat(response.updatedAt()).isNull();
    }

    @Test
    void getPreferences_shouldReturnSavedValues_whenPreferenceExists() {
        when(userPreferenceDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.of(
                new UserPreference("回答尽量简短", ReplyLanguage.ZH_CN, ResponseStyle.CONCISE, false, UPDATED_AT)));

        UserPreferenceResponse response = userPreferenceService.getPreferences(PUBLIC_ID);

        assertThat(response.instructions()).isEqualTo("回答尽量简短");
        assertThat(response.replyLanguage()).isEqualTo("zh-CN");
        assertThat(response.responseStyle()).isEqualTo("concise");
        assertThat(response.useHistory()).isFalse();
        assertThat(response.updatedAt()).isEqualTo(UPDATED_AT);
    }

    @Test
    void updatePreferences_shouldTrimInstructionsAndPersistEnumValues() {
        when(userPreferenceDirectory.upsert(any(), any())).thenReturn(true);
        when(userPreferenceDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.of(
                new UserPreference("回答尽量简短", ReplyLanguage.ZH_CN, ResponseStyle.CONCISE, false, UPDATED_AT)));

        UserPreferenceResponse response = userPreferenceService.updatePreferences(
                PUBLIC_ID, new UserPreferenceUpdateRequest("  回答尽量简短  ", "zh-CN", "concise", false));

        ArgumentCaptor<UserPreference> captor = ArgumentCaptor.forClass(UserPreference.class);
        verify(userPreferenceDirectory).upsert(any(), captor.capture());
        UserPreference saved = captor.getValue();
        assertThat(saved.instructions()).isEqualTo("回答尽量简短");
        assertThat(saved.replyLanguage()).isEqualTo(ReplyLanguage.ZH_CN);
        assertThat(saved.responseStyle()).isEqualTo(ResponseStyle.CONCISE);
        assertThat(saved.useHistory()).isFalse();
        assertThat(saved.updatedAt()).isNull();
        assertThat(response.updatedAt()).isEqualTo(UPDATED_AT);
    }

    @Test
    void updatePreferences_shouldTreatBlankInstructionsAsUnset() {
        when(userPreferenceDirectory.upsert(any(), any())).thenReturn(true);
        when(userPreferenceDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.of(
                new UserPreference(null, ReplyLanguage.AUTO, ResponseStyle.BALANCED, true, UPDATED_AT)));

        userPreferenceService.updatePreferences(
                PUBLIC_ID, new UserPreferenceUpdateRequest("   ", "auto", "balanced", true));

        ArgumentCaptor<UserPreference> captor = ArgumentCaptor.forClass(UserPreference.class);
        verify(userPreferenceDirectory).upsert(any(), captor.capture());
        assertThat(captor.getValue().instructions()).isNull();
    }

    @Test
    void updatePreferences_shouldThrowUnauthorized_whenUserIsMissing() {
        when(userPreferenceDirectory.upsert(any(), any())).thenReturn(false);

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userPreferenceService.updatePreferences(
                        PUBLIC_ID, new UserPreferenceUpdateRequest(null, "auto", "balanced", true)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.UNAUTHORIZED));
    }

    @Test
    void updatePreferences_shouldThrowParamInvalid_whenUseHistoryIsMissing() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userPreferenceService.updatePreferences(
                        PUBLIC_ID, new UserPreferenceUpdateRequest(null, "auto", "balanced", null)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));

        verify(userPreferenceDirectory, never()).upsert(any(), any());
    }

    @Test
    void updatePreferences_shouldThrowParamInvalid_whenReplyLanguageIsUnknown() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userPreferenceService.updatePreferences(
                        PUBLIC_ID, new UserPreferenceUpdateRequest(null, "fr-FR", "balanced", true)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));

        verify(userPreferenceDirectory, never()).upsert(any(), any());
    }
}
