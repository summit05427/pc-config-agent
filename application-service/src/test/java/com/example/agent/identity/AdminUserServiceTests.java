package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.AdminUserService;
import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.application.RefreshSessionService;
import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import com.example.agent.identity.web.dto.AdminUserListQuery;
import com.example.agent.identity.web.dto.AdminUserSummaryResponse;
import com.example.agent.shared.api.PageResult;
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

/**
 * 管理端用户服务单测：不启动 Spring 容器，外部依赖通过 Mockito 隔离。
 *
 * <p>重点覆盖业务约束而不是 SQL：禁用自己、移除最后一个启用管理员、
 * 状态/角色未变化时的幂等行为，以及审计写入点。</p>
 */
@ExtendWith(MockitoExtension.class)
class AdminUserServiceTests {

    private static final String PUBLIC_ID = "9d1a7f6e-2b3c-4d5e-8f90-1a2b3c4d5e6f";
    private static final String OTHER_PUBLIC_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
    private static final long USER_ID = 2L;
    private static final Instant CREATED_AT = Instant.parse("2026-10-29T08:00:00Z");
    private static final Instant UPDATED_AT = Instant.parse("2026-10-29T09:00:00Z");

    @Mock
    private UserDirectory userDirectory;

    @Mock
    private RefreshSessionService refreshSessionService;

    @Mock
    private AuthAuditRecorder authAuditRecorder;

    @InjectMocks
    private AdminUserService adminUserService;

    @Test
    void listUsers_shouldReturnEmptyPage_whenNoUserMatches() {
        AdminUserListQuery query = listQuery(" demo ", "", 1, 20);
        when(userDirectory.countUsers("demo", null)).thenReturn(0L);

        PageResult<AdminUserSummaryResponse> result = adminUserService.listUsers(query);

        assertThat(result.list()).isEmpty();
        assertThat(result.total()).isZero();
        assertThat(result.page()).isEqualTo(1);
        assertThat(result.size()).isEqualTo(20);
        verify(userDirectory, never()).listUsers(any(), any(), anyLong(), anyInt());
    }

    @Test
    void listUsers_shouldTrimKeywordAndMapPublicFieldsOnly() {
        AdminUserListQuery query = listQuery(" a@b.com ", "ACTIVE", 1, 20);
        when(userDirectory.countUsers("a@b.com", UserStatus.ACTIVE)).thenReturn(1L);
        when(userDirectory.listUsers("a@b.com", UserStatus.ACTIVE, 0L, 20))
                .thenReturn(List.of(profile(List.of("USER"), UserStatus.ACTIVE, null)));

        PageResult<AdminUserSummaryResponse> result = adminUserService.listUsers(query);

        assertThat(result.total()).isEqualTo(1);
        assertThat(result.list()).singleElement().satisfies(user -> {
            assertThat(user.publicId()).isEqualTo(PUBLIC_ID);
            assertThat(user.username()).isEqualTo("demo");
            assertThat(user.email()).isNull();
            assertThat(user.roles()).containsExactly("USER");
            assertThat(user.status()).isEqualTo("ACTIVE");
            assertThat(user.createdAt()).isEqualTo(CREATED_AT);
        });
    }

    @Test
    void updateStatus_shouldRejectMalformedPublicId() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminUserService.updateStatus("not-a-uuid", "DISABLED", OTHER_PUBLIC_ID))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(userDirectory, refreshSessionService, authAuditRecorder);
    }

    @Test
    void updateStatus_shouldThrowNotFound_whenUserMissing() {
        when(userDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.empty());

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminUserService.updateStatus(PUBLIC_ID, "DISABLED", OTHER_PUBLIC_ID))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_NOT_FOUND));
    }

    @Test
    void updateStatus_shouldRejectDisablingCurrentAdmin() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("ADMIN"), UserStatus.ACTIVE)));

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminUserService.updateStatus(PUBLIC_ID, "DISABLED", PUBLIC_ID))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_CONFLICT));
        verify(userDirectory, never()).updateStatus(any(), any());
        verifyNoInteractions(refreshSessionService, authAuditRecorder);
    }

    @Test
    void updateStatus_shouldRevokeSessionsAndRecordAudit_whenDisablingUser() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("USER"), UserStatus.ACTIVE)));
        when(userDirectory.updateStatus(PUBLIC_ID, UserStatus.DISABLED)).thenReturn(1);
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(List.of("USER"), UserStatus.DISABLED, UPDATED_AT)));

        AdminUserSummaryResponse response =
                adminUserService.updateStatus(PUBLIC_ID, "DISABLED", OTHER_PUBLIC_ID);

        assertThat(response.status()).isEqualTo("DISABLED");
        verify(refreshSessionService).revokeAllForDisabledUser(USER_ID);
        verify(authAuditRecorder).record(AuthAuditEvent.USER_DISABLED, "demo", PUBLIC_ID);
    }

    @Test
    void updateStatus_shouldBeIdempotent_whenStatusUnchanged() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("USER"), UserStatus.DISABLED)));
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(List.of("USER"), UserStatus.DISABLED, UPDATED_AT)));

        adminUserService.updateStatus(PUBLIC_ID, "DISABLED", OTHER_PUBLIC_ID);

        verify(userDirectory, never()).updateStatus(any(), any());
        verifyNoInteractions(refreshSessionService, authAuditRecorder);
    }

    @Test
    void updateRoles_shouldRejectRemovingLastActiveAdmin() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("ADMIN"), UserStatus.ACTIVE)));
        when(userDirectory.countActiveAdmins()).thenReturn(1L);

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminUserService.updateRoles(PUBLIC_ID, List.of("USER")))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_CONFLICT));
        verify(userDirectory, never()).updateRoles(any(), any());
        verifyNoInteractions(authAuditRecorder);
    }

    @Test
    void updateRoles_shouldAllowRemovingAdmin_whenAnotherActiveAdminExists() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("ADMIN"), UserStatus.ACTIVE)));
        when(userDirectory.countActiveAdmins()).thenReturn(2L);
        when(userDirectory.updateRoles(PUBLIC_ID, List.of("USER"))).thenReturn(1);
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(List.of("USER"), UserStatus.ACTIVE, UPDATED_AT)));

        AdminUserSummaryResponse response = adminUserService.updateRoles(PUBLIC_ID, List.of("USER"));

        assertThat(response.roles()).containsExactly("USER");
        verify(authAuditRecorder).record(AuthAuditEvent.ROLE_CHANGED, "demo", PUBLIC_ID);
    }

    @Test
    void updateRoles_shouldNotWriteOrAudit_whenRolesUnchanged() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("USER"), UserStatus.ACTIVE)));
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(List.of("USER"), UserStatus.ACTIVE, UPDATED_AT)));

        // 重复元素去重后与现有角色相同，按幂等处理
        adminUserService.updateRoles(PUBLIC_ID, List.of("USER", "USER"));

        verify(userDirectory, never()).updateRoles(any(), any());
        verify(userDirectory, never()).countActiveAdmins();
        verifyNoInteractions(authAuditRecorder);
    }

    @Test
    void updateRoles_shouldPersistAndRecordAudit_whenRolesChange() {
        when(userDirectory.findByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(account(List.of("USER"), UserStatus.ACTIVE)));
        when(userDirectory.updateRoles(PUBLIC_ID, List.of("USER", "ADMIN"))).thenReturn(1);
        when(userDirectory.findProfileByPublicId(PUBLIC_ID))
                .thenReturn(Optional.of(profile(List.of("USER", "ADMIN"), UserStatus.ACTIVE, UPDATED_AT)));

        AdminUserSummaryResponse response =
                adminUserService.updateRoles(PUBLIC_ID, List.of("USER", "ADMIN", "USER"));

        // 去重保序：按调用方首次出现的顺序写库
        assertThat(response.roles()).containsExactly("USER", "ADMIN");
        verify(authAuditRecorder).record(AuthAuditEvent.ROLE_CHANGED, "demo", PUBLIC_ID);
    }

    @Test
    void updateRoles_shouldThrowNotFound_whenUserMissing() {
        when(userDirectory.findByPublicId(PUBLIC_ID)).thenReturn(Optional.empty());

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminUserService.updateRoles(PUBLIC_ID, List.of("USER")))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_NOT_FOUND));
        verifyNoInteractions(authAuditRecorder);
    }

    private static AdminUserListQuery listQuery(String keyword, String status, int page, int size) {
        AdminUserListQuery query = new AdminUserListQuery();
        query.setKeyword(keyword);
        query.setStatus(status);
        query.setPage(page);
        query.setSize(size);
        return query;
    }

    private static UserAccount account(List<String> roles, UserStatus status) {
        return new UserAccount(USER_ID, PUBLIC_ID, "demo", "$2a$10$test-hash", List.copyOf(roles), status);
    }

    private static UserProfile profile(List<String> roles, UserStatus status, Instant updatedAt) {
        return new UserProfile(
                PUBLIC_ID,
                "demo",
                null,
                null,
                null,
                List.copyOf(roles),
                status,
                CREATED_AT,
                updatedAt == null ? CREATED_AT : updatedAt);
    }
}
