package com.example.agent.identity.web;

import com.example.agent.identity.application.UserPreferenceService;
import com.example.agent.identity.web.dto.UserPreferenceResponse;
import com.example.agent.identity.web.dto.UserPreferenceUpdateRequest;
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
 * 用户偏好接口。
 *
 * <p>固定走 {@code /users/me/preferences}：只读写令牌 {@code sub} 对应的本人偏好，
 * 不提供按 ID 访问的入口。偏好不参与鉴权，仅用于对话时拼装 system prompt。</p>
 */
@RestController
@RequestMapping("/api/v1/users/me/preferences")
@RequiredArgsConstructor
public class UserPreferenceController {

    private final UserPreferenceService userPreferenceService;

    @Operation(summary = "获取用户偏好", description = "未保存过时返回默认值，updatedAt 为 null")
    @GetMapping
    public ApiResponse<UserPreferenceResponse> getPreferences(Authentication authentication) {
        return ApiResponse.success(userPreferenceService.getPreferences(authentication.getName()));
    }

    @Operation(summary = "更新用户偏好", description = "全量提交指令、回复语言、回复风格与是否使用历史")
    @PutMapping
    public ApiResponse<UserPreferenceResponse> updatePreferences(
            @Valid @RequestBody UserPreferenceUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(userPreferenceService.updatePreferences(authentication.getName(), request));
    }
}
