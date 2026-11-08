package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import com.example.agent.identity.web.dto.AdminUserListQuery;
import com.example.agent.identity.web.dto.AdminUserSummaryResponse;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 管理端用户管理服务。
 *
 * <p>鉴权由 {@code SecurityConfig} 的 {@code /api/v1/admin/**} 规则统一完成，
 * 本层只负责业务约束：不能禁用自己、不能移除最后一个启用管理员、
 * 角色未变化时不写库也不记审计。</p>
 */
@Service
@RequiredArgsConstructor
public class AdminUserService {

    private static final String ADMIN_ROLE = "ADMIN";

    private final UserDirectory userDirectory;
    private final RefreshSessionService refreshSessionService;
    private final AuthAuditRecorder authAuditRecorder;

    /**
     * 分页查询用户，支持登录名/邮箱模糊匹配与状态过滤。
     *
     * @param query 查询参数
     * @return 分页结果
     */
    @Transactional(readOnly = true)
    public PageResult<AdminUserSummaryResponse> listUsers(AdminUserListQuery query) {
        UserStatus status = parseStatus(query.getStatus());
        String keyword = normalizeKeyword(query.getKeyword());
        long total = userDirectory.countUsers(keyword, status);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminUserSummaryResponse> users = userDirectory
                .listUsers(keyword, status, query.offset(), query.getSize()).stream()
                .map(AdminUserService::toSummary)
                .toList();
        return PageResult.of(users, total, query);
    }

    /**
     * 变更账号状态；禁用时撤销该用户全部刷新会话并记审计。
     *
     * @param publicId        目标用户公开 ID
     * @param status          目标状态，取值已由请求 DTO 限定
     * @param currentPublicId 当前登录管理员的公开 ID，用于拦截「禁用自己」
     * @return 更新后的用户摘要
     * @throws BusinessException 标识格式非法（400）、目标不存在（404）、禁用自己（409）
     */
    @Transactional
    public AdminUserSummaryResponse updateStatus(String publicId, String status, String currentPublicId) {
        UserAccount account = requireUser(publicId);
        UserStatus targetStatus = UserStatus.valueOf(status);
        if (targetStatus == UserStatus.DISABLED && account.publicId().equals(currentPublicId)) {
            throw new BusinessException(CommonErrorCode.RESOURCE_CONFLICT, "不能禁用当前登录的管理员");
        }
        // 状态未变化保持幂等：不重复撤销会话，也不重复写审计
        if (account.status() == targetStatus) {
            return toSummary(requireProfile(account.publicId()));
        }
        if (userDirectory.updateStatus(account.publicId(), targetStatus) == 0) {
            throw userNotFound();
        }
        if (targetStatus == UserStatus.DISABLED) {
            refreshSessionService.revokeAllForDisabledUser(account.id());
            authAuditRecorder.record(AuthAuditEvent.USER_DISABLED, account.username(), account.publicId());
        }
        return toSummary(requireProfile(account.publicId()));
    }

    /**
     * 替换账号角色；角色未变化时不写库、不记审计。
     *
     * @param publicId 目标用户公开 ID
     * @param roles    目标角色，白名单已由请求 DTO 限定
     * @return 更新后的用户摘要
     * @throws BusinessException 标识格式非法（400）、目标不存在（404）、
     *                           移除最后一个启用管理员（409）
     */
    @Transactional
    public AdminUserSummaryResponse updateRoles(String publicId, List<String> roles) {
        UserAccount account = requireUser(publicId);
        List<String> normalizedRoles = normalizeRoles(roles);
        if (sameRoles(account.roles(), normalizedRoles)) {
            return toSummary(requireProfile(account.publicId()));
        }
        if (isActiveAdmin(account)
                && !normalizedRoles.contains(ADMIN_ROLE)
                && userDirectory.countActiveAdmins() <= 1) {
            throw new BusinessException(CommonErrorCode.RESOURCE_CONFLICT, "不能移除最后一个启用状态的管理员");
        }
        if (userDirectory.updateRoles(account.publicId(), normalizedRoles) == 0) {
            throw userNotFound();
        }
        // 角色变更必须留痕：补齐 auth_audit_logs 白名单中最后一个缺口
        authAuditRecorder.record(AuthAuditEvent.ROLE_CHANGED, account.username(), account.publicId());
        return toSummary(requireProfile(account.publicId()));
    }

    /** 路径参数是客户端输入，先校验格式再交给 SQL，避免非法 UUID 变成 500。 */
    private UserAccount requireUser(String publicId) {
        if (!isUuid(publicId)) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "用户标识格式不正确");
        }
        return userDirectory.findByPublicId(publicId).orElseThrow(AdminUserService::userNotFound);
    }

    private UserProfile requireProfile(String publicId) {
        return userDirectory.findProfileByPublicId(publicId).orElseThrow(AdminUserService::userNotFound);
    }

    private static boolean isUuid(String value) {
        try {
            UUID.fromString(value);
            return true;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static BusinessException userNotFound() {
        return new BusinessException(CommonErrorCode.RESOURCE_NOT_FOUND, "目标用户不存在");
    }

    /** 空白状态表示不过滤；取值白名单由请求 DTO 的 {@code @Pattern} 保证。 */
    private static UserStatus parseStatus(String value) {
        return value == null || value.isBlank() ? null : UserStatus.valueOf(value);
    }

    /**
     * 只做用户输入的空白归一化；{@code LIKE} 通配符属于持久化细节，由 UserDirectory 实现负责拼接。
     */
    private static String normalizeKeyword(String keyword) {
        return keyword == null || keyword.isBlank() ? null : keyword.trim();
    }

    /** 去重但保留顺序：角色的排列顺序不影响授权，写库仍按调用方意图保存。 */
    private static List<String> normalizeRoles(List<String> roles) {
        return List.copyOf(new LinkedHashSet<>(roles));
    }

    private static boolean sameRoles(List<String> current, List<String> target) {
        Set<String> currentSet = Set.copyOf(current);
        Set<String> targetSet = Set.copyOf(target);
        return currentSet.equals(targetSet);
    }

    private static boolean isActiveAdmin(UserAccount account) {
        return account.status().isActive() && account.roles().contains(ADMIN_ROLE);
    }

    private static AdminUserSummaryResponse toSummary(UserProfile profile) {
        return new AdminUserSummaryResponse(
                profile.publicId(),
                profile.username(),
                profile.email(),
                profile.roles(),
                profile.status().name(),
                profile.createdAt());
    }
}
