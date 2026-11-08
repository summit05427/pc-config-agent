package com.example.agent.identity.web;

import com.example.agent.identity.application.UserPasswordService;
import com.example.agent.identity.web.dto.UserPasswordChangeRequest;
import com.example.agent.shared.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 账号口令接口。
 *
 * <p>与资料接口共用 {@code /users/me} 前缀：口令同样只能由本人修改，
 * 不提供按 ID 的入口。当前设备靠访问令牌的 {@code sid} claim 识别，
 * 而不是刷新 Cookie——后者的 Path 限定在 {@code /api/v1/auth}，不会随本请求发送。</p>
 */
@RestController
@RequestMapping("/api/v1/users/me")
@RequiredArgsConstructor
public class UserPasswordController {

    private final UserPasswordService userPasswordService;

    @Operation(summary = "修改密码", description = "校验当前口令后更新摘要，并撤销其他设备的登录会话")
    @PutMapping("/password")
    public ApiResponse<Void> changePassword(
            @Valid @RequestBody UserPasswordChangeRequest request,
            Authentication authentication) {
        userPasswordService.changePassword(
                authentication.getName(), AccessTokenClaims.currentFamilyId(authentication), request);
        return ApiResponse.success();
    }
}
