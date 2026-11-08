package com.example.agent.model.web;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.domain.ProviderSummary;
import com.example.agent.shared.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * BYOK 供应商目录接口（v2）。
 *
 * <p>设置页「添加供应商」必须使用这个端点，而不是从模型目录反推：
 * Provider 可能暂时没有启用模型，但仍然允许用户先接入密钥。</p>
 */
@RestController
@RequestMapping("/api/v2/model-providers")
@RequiredArgsConstructor
public class ModelProviderV2Controller {

    private final ModelCatalogService modelCatalogService;

    /**
     * @return 协议受支持且已启用的 Provider 列表；运行时未启用时返回 404
     */
    @Operation(summary = "查询 BYOK 可接入的 Provider", description = "只返回协议受支持且已启用的供应商")
    @GetMapping
    public ApiResponse<List<ProviderSummary>> listProviders() {
        return ApiResponse.success(modelCatalogService.listProviders());
    }
}
