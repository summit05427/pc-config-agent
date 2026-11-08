package com.example.agent.model.web;

import com.example.agent.model.application.ServiceTokenService;
import com.example.agent.model.web.dto.ServiceTokenResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.security.IssuedToken;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 服务令牌签发接口，仅供 Agent 在容器网络内调用，不经 Nginx 暴露。
 *
 * <p>凭据走表单而不是 JSON：避免被前端误调用，也避免凭据出现在 URL 查询串里。</p>
 */
@RestController
@RequestMapping("/internal/v1/auth")
@RequiredArgsConstructor
public class InternalAuthController {

    private final ServiceTokenService serviceTokenService;

    /**
     * @param clientId     调用方标识
     * @param clientSecret 调用方密钥
     * @return Bearer 令牌与有效期
     */
    @PostMapping("/service-token")
    public ApiResponse<ServiceTokenResponse> issueServiceToken(
            @RequestParam("client_id") @NotBlank String clientId,
            @RequestParam("client_secret") @NotBlank String clientSecret) {
        IssuedToken issued = serviceTokenService.issue(clientId, clientSecret);
        return ApiResponse.success(
                new ServiceTokenResponse(issued.value(), "Bearer", issued.expiresInSeconds()));
    }
}
