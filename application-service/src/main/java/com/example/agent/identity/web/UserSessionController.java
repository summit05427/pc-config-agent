package com.example.agent.identity.web;

import com.example.agent.identity.application.RefreshSessionService;
import com.example.agent.identity.web.dto.SessionResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 登录设备接口。
 *
 * <p>与资料、口令接口共用 {@code /users/me} 前缀：设备属于当前登录用户，
 * 不接受按用户 ID 访问，归属校验由服务层结合令牌 {@code sub} 完成。</p>
 */
@RestController
@RequestMapping("/api/v1/users/me/sessions")
@RequiredArgsConstructor
public class UserSessionController {

    private final RefreshSessionService refreshSessionService;

    @Operation(summary = "查询登录设备", description = "按令牌族聚合，current 标记当前设备；只返回仍然有效的设备")
    @GetMapping
    public ApiResponse<PageResult<SessionResponse>> listSessions(
            @Valid PageQuery pageQuery,
            Authentication authentication) {
        return ApiResponse.success(refreshSessionService.listFamilies(
                authentication.getName(), AccessTokenClaims.currentFamilyId(authentication), pageQuery));
    }

    @Operation(summary = "撤销指定设备", description = "不能撤销当前设备，需改走 /api/v1/auth/logout")
    @DeleteMapping("/{familyId}")
    public ApiResponse<Void> deleteSession(
            @PathVariable String familyId,
            Authentication authentication) {
        refreshSessionService.revokeFamily(
                authentication.getName(), familyId, AccessTokenClaims.currentFamilyId(authentication));
        return ApiResponse.success();
    }
}
