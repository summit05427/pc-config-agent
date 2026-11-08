package com.example.agent.model.web;

import com.example.agent.model.application.AdminModelCatalogService;
import com.example.agent.model.web.dto.AdminModelListQuery;
import com.example.agent.model.web.dto.AdminModelPricingCreateRequest;
import com.example.agent.model.web.dto.AdminModelPricingResponse;
import com.example.agent.model.web.dto.AdminModelStatusUpdateRequest;
import com.example.agent.model.web.dto.AdminModelSummaryResponse;
import com.example.agent.model.web.dto.AdminProviderStatusUpdateRequest;
import com.example.agent.model.web.dto.AdminProviderSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端模型目录与定价接口。
 *
 * <p>{@code /api/v1/admin/**} 由安全配置统一限制为 {@code ADMIN}，
 * Controller 内不做角色判断，只把当前管理员登录名传给服务层用于变更留痕。</p>
 */
@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class AdminModelCatalogController {

    private final AdminModelCatalogService adminModelCatalogService;

    @Operation(summary = "分页查询模型目录", description = "含停用条目；支持关键字、Provider 与启用状态过滤")
    @GetMapping("/models")
    public ApiResponse<PageResult<AdminModelSummaryResponse>> listModels(@Valid AdminModelListQuery query) {
        return ApiResponse.success(adminModelCatalogService.listModels(query));
    }

    @Operation(summary = "启用或停用模型", description = "停用只影响后续调用解析，不删除目录条目")
    @PatchMapping("/models/{provider}/{modelKey}/status")
    public ApiResponse<AdminModelSummaryResponse> updateModelStatus(
            @PathVariable String provider,
            @PathVariable String modelKey,
            @Valid @RequestBody AdminModelStatusUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(adminModelCatalogService.updateModelStatus(
                provider, modelKey, Boolean.TRUE.equals(request.enabled()), authentication.getName()));
    }

    @Operation(summary = "分页查询模型定价版本", description = "按生效时间倒序，最新版本在前")
    @GetMapping("/models/{provider}/{modelKey}/pricing")
    public ApiResponse<PageResult<AdminModelPricingResponse>> listPricing(
            @PathVariable String provider,
            @PathVariable String modelKey,
            @Valid PageQuery query) {
        return ApiResponse.success(adminModelCatalogService.listPricing(provider, modelKey, query));
    }

    @Operation(summary = "新增模型定价版本", description = "只追加版本；同一生效时间重复提交返回 409")
    @PostMapping("/models/{provider}/{modelKey}/pricing")
    public ApiResponse<AdminModelPricingResponse> createPricing(
            @PathVariable String provider,
            @PathVariable String modelKey,
            @Valid @RequestBody AdminModelPricingCreateRequest request,
            Authentication authentication) {
        return ApiResponse.success(adminModelCatalogService.createPricing(
                provider, modelKey, request, authentication.getName()));
    }

    @Operation(summary = "查询 Provider 目录", description = "含停用 Provider 与模型数量统计，供筛选与启停")
    @GetMapping("/model-providers")
    public ApiResponse<List<AdminProviderSummaryResponse>> listProviders() {
        return ApiResponse.success(adminModelCatalogService.listProviders());
    }

    @Operation(summary = "启用或停用 Provider", description = "停用后其下模型即使启用也不可用")
    @PatchMapping("/model-providers/{code}/status")
    public ApiResponse<AdminProviderSummaryResponse> updateProviderStatus(
            @PathVariable String code,
            @Valid @RequestBody AdminProviderStatusUpdateRequest request,
            Authentication authentication) {
        return ApiResponse.success(adminModelCatalogService.updateProviderStatus(
                code, Boolean.TRUE.equals(request.enabled()), authentication.getName()));
    }
}
