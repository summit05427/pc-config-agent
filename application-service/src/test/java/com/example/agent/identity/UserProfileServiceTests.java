package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.application.UserProfileService;
import com.example.agent.identity.domain.IdentityErrorCode;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import com.example.agent.identity.web.dto.UserProfileResponse;
import com.example.agent.identity.web.dto.UserProfileUpdateRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

/**
 * 个人资料服务单测：不启动 Spring 容器，外部依赖通过 Mockito 隔离。
 */
@ExtendWith(MockitoExtension.class)
class UserProfileServiceTests {

    private static final String PUBLIC_ID = "9d1a7f6e-2b3c-4d5e-8f90-1a2b3c4d5e6f";
    private static final Instant CREATED_AT = Instant.parse("2026-10-29T08:00:00Z");
    private static final Instant UPDATED_AT = Instant.parse("2026-10-29T09:00:00Z");

    @Mock
    private UserDirectory userDirectory;

    @InjectMocks
    private UserProfileService userProfileService;

    @Test
    void getProfile_shouldReturnPublicFieldsOnly_whenUserExists() {
        when(userDirectory.findProfileByPublicId(PUBLIC_ID)).thenReturn(Optional.of(profile(
                null, null, null, CREATED_AT)));

        UserProfileResponse response = userProfileService.getProfile(PUBLIC_ID);

        assertThat(response.publicId()).isEqualTo(PUBLIC_ID);
        assertThat(response.username()).isEqualTo("demo");
        assertThat(response.roles()).containsExactly("USER");
        assertThat(response.status()).isEqualTo("ACTIVE");
        assertThat(response.displayName()).isNull();
        assertThat(response.createdAt()).isEqualTo(CREATED_AT);
    }

    @Test
    void getProfile_shouldThrowUnauthorized_whenUserIsMissing() {
        when(userDirectory.findProfileByPublicId(PUBLIC_ID)).thenReturn(Optional.empty());

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userProfileService.getProfile(PUBLIC_ID))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.UNAUTHORIZED));
    }

    @Test
    void updateProfile_shouldTrimValuesAndNormalizeBlankFieldsToNull() {
        UserProfileUpdateRequest request = new UserProfileUpdateRequest("  小明  ", "   ", "   ");
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(null, null, null, CREATED_AT)))
                .thenReturn(Optional.of(profile("小明", null, null, UPDATED_AT)));

        UserProfileResponse response = userProfileService.updateProfile(PUBLIC_ID, request);

        verify(userDirectory).updateProfile(PUBLIC_ID, "小明", null, null);
        assertThat(response.displayName()).isEqualTo("小明");
        assertThat(response.email()).isNull();
        assertThat(response.bio()).isNull();
        assertThat(response.updatedAt()).isEqualTo(UPDATED_AT);
    }

    @Test
    void updateProfile_shouldThrowParamInvalid_whenDisplayNameIsBlank() {
        when(userDirectory.findProfileByPublicId(PUBLIC_ID)).thenReturn(Optional.of(profile(
                null, null, null, CREATED_AT)));

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userProfileService.updateProfile(
                        PUBLIC_ID, new UserProfileUpdateRequest("   ", null, null)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
    }

    @Test
    void updateProfile_shouldThrowEmailTaken_whenEmailViolatesUniqueConstraint() {
        when(userDirectory.findProfileByPublicId(PUBLIC_ID)).thenReturn(Optional.of(profile(
                null, null, null, CREATED_AT)));
        doThrow(new DataIntegrityViolationException("duplicate email"))
                .when(userDirectory)
                .updateProfile(anyString(), anyString(), any(), any());

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> userProfileService.updateProfile(
                        PUBLIC_ID, new UserProfileUpdateRequest("小明", "a@b.com", null)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(IdentityErrorCode.EMAIL_TAKEN));
    }

    private static UserProfile profile(String displayName, String email, String bio, Instant updatedAt) {
        return new UserProfile(
                PUBLIC_ID,
                "demo",
                displayName,
                email,
                bio,
                List.of("USER"),
                UserStatus.ACTIVE,
                CREATED_AT,
                updatedAt);
    }
}
