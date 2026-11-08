package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.application.RefreshSessionService;
import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.application.UserPasswordService;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserStatus;
import com.example.agent.identity.web.dto.UserPasswordChangeRequest;
import com.example.agent.shared.error.BusinessException;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 修改口令服务单元测试。
 *
 * <p>口令比对与摘要编码用 Mockito 隔离，重点验证「哪种情况必须拒绝、
 * 拒绝时不得写库也不得撤会话」以及成功路径的撤销范围。</p>
 */
@ExtendWith(MockitoExtension.class)
class UserPasswordServiceTests {

    private static final Long USER_ID = 7L;
    private static final String PUBLIC_ID = UUID.randomUUID().toString();
    private static final String CURRENT_HASH = "current-hash";
    private static final String CURRENT_PASSWORD = "old-password";
    private static final String NEW_PASSWORD = "new-password";
    private static final String NEW_HASH = "new-hash";
    private static final UUID FAMILY_ID = UUID.randomUUID();

    @Mock
    private UserDirectory userDirectory;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private RefreshSessionService refreshSessionService;

    @Mock
    private AuthAuditRecorder authAuditRecorder;

    @InjectMocks
    private UserPasswordService userPasswordService;

    private UserPasswordChangeRequest request;

    @BeforeEach
    void setUp() {
        when(userDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.of(new UserAccount(
                USER_ID, PUBLIC_ID, "admin", CURRENT_HASH, List.of("USER"), UserStatus.ACTIVE)));
        request = new UserPasswordChangeRequest(CURRENT_PASSWORD, NEW_PASSWORD);
    }

    @Test
    void changePassword_shouldUpdateHashAndRevokeOtherSessions() {
        when(passwordEncoder.matches(CURRENT_PASSWORD, CURRENT_HASH)).thenReturn(true);
        when(passwordEncoder.matches(NEW_PASSWORD, CURRENT_HASH)).thenReturn(false);
        when(passwordEncoder.encode(NEW_PASSWORD)).thenReturn(NEW_HASH);

        userPasswordService.changePassword(PUBLIC_ID, FAMILY_ID.toString(), request);

        verify(userDirectory).updatePasswordHash(PUBLIC_ID, NEW_HASH);
        verify(refreshSessionService).revokeAllExceptFamily(USER_ID, FAMILY_ID);
    }

    @Test
    void changePassword_shouldRejectWrongCurrentPasswordWithoutSideEffects() {
        when(passwordEncoder.matches(CURRENT_PASSWORD, CURRENT_HASH)).thenReturn(false);

        assertThatThrownBy(() -> userPasswordService.changePassword(PUBLIC_ID, FAMILY_ID.toString(), request))
                .isInstanceOf(BusinessException.class);

        verify(userDirectory, never()).updatePasswordHash(anyString(), anyString());
        verifyNoInteractions(refreshSessionService);
    }

    @Test
    void changePassword_shouldRejectSamePassword() {
        when(passwordEncoder.matches(CURRENT_PASSWORD, CURRENT_HASH)).thenReturn(true);
        when(passwordEncoder.matches(NEW_PASSWORD, CURRENT_HASH)).thenReturn(true);

        assertThatThrownBy(() -> userPasswordService.changePassword(PUBLIC_ID, FAMILY_ID.toString(), request))
                .isInstanceOf(BusinessException.class);

        verify(userDirectory, never()).updatePasswordHash(anyString(), anyString());
        verifyNoInteractions(refreshSessionService);
    }

    @Test
    void changePassword_shouldRejectTokenWithoutSessionClaim() {
        assertThatThrownBy(() -> userPasswordService.changePassword(PUBLIC_ID, null, request))
                .isInstanceOf(BusinessException.class);

        // 无法识别当前设备时直接要求重新登录，不写库也不撤会话
        verify(userDirectory, never()).updatePasswordHash(anyString(), anyString());
        verifyNoInteractions(passwordEncoder, refreshSessionService);
    }

    @Test
    void changePassword_shouldRejectUnknownUser() {
        when(userDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userPasswordService.changePassword(PUBLIC_ID, FAMILY_ID.toString(), request))
                .isInstanceOf(BusinessException.class);

        verifyNoInteractions(passwordEncoder, refreshSessionService);
    }
}
