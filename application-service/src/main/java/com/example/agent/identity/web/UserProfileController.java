package com.example.agent.identity.web;

import com.example.agent.identity.application.UserProfileService;
import com.example.agent.identity.web.dto.UserProfileResponse;
import com.example.agent.identity.web.dto.UserProfileUpdateRequest;
import com.example.agent.shared.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 个人资料接口。
 *
 * <p>{@code me} 是固定路径而不是 {@code /users/{id}}：用户只能读写自己的资料，
 * 不暴露按 ID 访问的入口，也就不存在越权校验的漏点。</p>
 */
@RestController
@RequestMapping("/api/v1/users/me")
@RequiredArgsConstructor
public class UserProfileController {

    private final UserProfileService userProfileService;

    @Operation(summary = "获取个人资料", description = "返回展示名、邮箱、简介与角色；不含内部主键")
    @GetMapping("/profile")
    public ApiResponse<UserProfileResponse> getProfile(Authentication authentication) {
        return ApiResponse.success(userProfileService.getProfile(authentication.getName()));
    }

    @Operation(summary = "更新个人资料", description = "全量更新展示名、邮箱、简介；登录名与角色不可在此修改")
    @PutMapping("/profile")
    public ApiResponse<UserProfileResponse> updateProfile(
            @Valid @RequestBody UserProfileUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(userProfileService.updateProfile(authentication.getName(), request));
    }
}
