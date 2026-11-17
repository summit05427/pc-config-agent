package com.example.agent.model.web;

import com.example.agent.model.application.ProviderConnectionService;
import com.example.agent.model.web.dto.ModelConnectionCreateRequest;
import com.example.agent.model.web.dto.ModelConnectionResponse;
import com.example.agent.model.web.dto.ModelConnectionUpdateRequest;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.security.CurrentUser;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * BYOK 连接与凭证接口。
 *
 * <p>固定路径 {@code /model-connections}，不提供 {@code /credentials} 回读端点：
 * 密钥只进不出，响应只有掩码。</p>
 */
@RestController
@RequestMapping("/api/v1/model-connections")
@RequiredArgsConstructor
public class ModelConnectionController {

    private final ProviderConnectionService providerConnectionService;

    @Operation(summary = "列出模型连接", description = "只返回掩码与状态，不含明文密钥")
    @GetMapping
    public ApiResponse<List<ModelConnectionResponse>> list(Authentication authentication) {
        List<ModelConnectionResponse> connections = providerConnectionService
                .list(CurrentUser.id(authentication)).stream()
                .map(ModelConnectionResponse::from)
                .toList();
        return ApiResponse.success(connections);
    }

    @Operation(summary = "创建模型连接", description = "保存加密凭证；重复创建同一 Provider 返回 409")
    @PostMapping
    public ApiResponse<ModelConnectionResponse> create(
            @Valid @RequestBody ModelConnectionCreateRequest request,
            Authentication authentication) {
        return ApiResponse.success(ModelConnectionResponse.from(providerConnectionService.create(
                CurrentUser.id(authentication), request.providerCode(), request.baseUrl(), request.apiKey())));
    }

    @Operation(
            summary = "轮换凭证",
            description = "撤销旧凭证并写入新密钥；地址变更会清空旧验证时间，保存后自动验证一次")
    @PutMapping("/{connectionId}")
    public ApiResponse<ModelConnectionResponse> update(
            @PathVariable UUID connectionId,
            @Valid @RequestBody ModelConnectionUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(ModelConnectionResponse.from(providerConnectionService.update(
                CurrentUser.id(authentication), connectionId, request.baseUrl(), request.apiKey())));
    }

    @Operation(
            summary = "验证凭证",
            description = "先本地校验密文与掩码，再探测 Provider（GET /models，不支持时退化为最小 chat）；"
                    + "成功写入 lastVerifiedAt 并置凭证为 VERIFIED，上游明确拒绝时置为 INVALID")
    @PostMapping("/{connectionId}/verify")
    public ApiResponse<ModelConnectionResponse> verify(
            @PathVariable UUID connectionId,
            Authentication authentication) {
        return ApiResponse.success(ModelConnectionResponse.from(
                providerConnectionService.verify(CurrentUser.id(authentication), connectionId)));
    }

    @Operation(summary = "删除模型连接", description = "软删除连接并撤销凭证，撤销后不可再使用")
    @DeleteMapping("/{connectionId}")
    public ApiResponse<Void> delete(
            @PathVariable UUID connectionId,
            Authentication authentication) {
        providerConnectionService.delete(CurrentUser.id(authentication), connectionId);
        return ApiResponse.success();
    }
}
