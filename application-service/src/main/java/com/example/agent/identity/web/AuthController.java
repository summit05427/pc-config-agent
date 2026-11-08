package com.example.agent.identity.web;

import com.example.agent.identity.application.AuthService;
import com.example.agent.identity.web.dto.CurrentUserResponse;
import com.example.agent.identity.web.dto.LoginRequest;
import com.example.agent.identity.web.dto.LoginResponse;
import com.example.agent.identity.web.dto.RefreshResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.security.RequestOriginValidator;
import com.example.agent.shared.web.ClientIpResolver;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 认证接口。
 *
 * <p>刷新令牌只走 HttpOnly Cookie，响应体永远不含它；
 * 依赖 Cookie 的两个接口在服务端额外做来源校验，避免被跨站页面伪造。</p>
 */
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthController {

    private static final String TOKEN_TYPE = "Bearer";

    private final AuthService authService;
    private final RefreshCookieFactory refreshCookieFactory;
    private final RequestOriginValidator requestOriginValidator;

    @Operation(summary = "账号密码登录", description = "返回访问令牌并下发 HttpOnly 刷新 Cookie")
    @SecurityRequirements
    @PostMapping("/login")
    public ApiResponse<LoginResponse> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest servletRequest,
            HttpServletResponse response) {
        AuthService.LoginResult result = authService.login(request, ClientIpResolver.resolve(servletRequest));
        writeRefreshCookie(response, refreshCookieFactory.create(result.rawRefreshToken(), result.refreshExpiresAt()));
        return ApiResponse.success(new LoginResponse(
                result.accessToken(), TOKEN_TYPE, result.expiresInSeconds(), result.user()));
    }

    @Operation(summary = "刷新访问令牌", description = "用 HttpOnly Cookie 中的刷新令牌轮换，Cookie 缺失或失效返回 401")
    @SecurityRequirements
    @PostMapping("/refresh")
    public ApiResponse<RefreshResponse> refresh(
            @CookieValue(name = RefreshCookieFactory.COOKIE_NAME, required = false) String refreshToken,
            HttpServletRequest request,
            HttpServletResponse response) {
        requestOriginValidator.requireTrustedOrigin(request);
        AuthService.RefreshResult result = authService.refresh(refreshToken);
        writeRefreshCookie(response, refreshCookieFactory.create(result.rawRefreshToken(), result.refreshExpiresAt()));
        return ApiResponse.success(
                new RefreshResponse(result.accessToken(), TOKEN_TYPE, result.expiresInSeconds()));
    }

    @Operation(summary = "退出登录", description = "撤销当前刷新会话并清除 Cookie，未登录时同样返回成功")
    @SecurityRequirements
    @PostMapping("/logout")
    public ApiResponse<Void> logout(
            @CookieValue(name = RefreshCookieFactory.COOKIE_NAME, required = false) String refreshToken,
            HttpServletRequest request,
            HttpServletResponse response) {
        requestOriginValidator.requireTrustedOrigin(request);
        authService.logout(refreshToken);
        writeRefreshCookie(response, refreshCookieFactory.clear());
        return ApiResponse.success();
    }

    @Operation(summary = "退出所有设备", description = "撤销该用户全部刷新会话并清除当前 Cookie；需访问令牌")
    @PostMapping("/logout-all")
    public ApiResponse<Void> logoutAll(Authentication authentication, HttpServletResponse response) {
        authService.logoutAll(authentication.getName());
        writeRefreshCookie(response, refreshCookieFactory.clear());
        return ApiResponse.success();
    }

    @Operation(summary = "获取当前登录用户", description = "前端刷新页面后用它恢复用户信息与角色")
    @GetMapping("/me")
    public ApiResponse<CurrentUserResponse> me(Authentication authentication) {
        return ApiResponse.success(authService.currentUser(authentication));
    }

    private static void writeRefreshCookie(HttpServletResponse response, ResponseCookie cookie) {
        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
    }
}
