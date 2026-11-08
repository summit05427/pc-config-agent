package com.example.agent.identity.web;

import com.example.agent.identity.application.AdminUserService;
import com.example.agent.identity.web.dto.AdminUserListQuery;
import com.example.agent.identity.web.dto.AdminUserRolesUpdateRequest;
import com.example.agent.identity.web.dto.AdminUserStatusUpdateRequest;
import com.example.agent.identity.web.dto.AdminUserSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端用户接口。
 *
 * <p>{@code /api/v1/admin/**} 由安全配置统一限制为 {@code ADMIN}，
 * 因此 Controller 内不做角色判断，只把当前管理员公开 ID 传给服务层用于拦截危险操作。</p>
 */
@RestController
@RequestMapping("/api/v1/admin/users")
@RequiredArgsConstructor
public class AdminUserController {

    private final AdminUserService adminUserService;

    @Operation(summary = "分页查询用户", description = "支持登录名/邮箱模糊匹配与状态过滤，按创建时间倒序")
    @GetMapping
    public ApiResponse<PageResult<AdminUserSummaryResponse>> listUsers(@Valid AdminUserListQuery query) {
        return ApiResponse.success(adminUserService.listUsers(query));
    }

    @Operation(summary = "变更账号状态", description = "禁用会撤销该用户全部刷新会话；不能禁用当前登录的管理员")
    @PatchMapping("/{publicId}/status")
    public ApiResponse<AdminUserSummaryResponse> updateStatus(
            @PathVariable String publicId,
            @Valid @RequestBody AdminUserStatusUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(
                adminUserService.updateStatus(publicId, request.status(), authentication.getName()));
    }

    @Operation(summary = "替换账号角色", description = "白名单仅 USER/ADMIN；不能移除最后一个启用状态的管理员")
    @PatchMapping("/{publicId}/roles")
    public ApiResponse<AdminUserSummaryResponse> updateRoles(
            @PathVariable String publicId,
            @Valid @RequestBody AdminUserRolesUpdateRequest request) {
        return ApiResponse.success(adminUserService.updateRoles(publicId, request.roles()));
    }
}
