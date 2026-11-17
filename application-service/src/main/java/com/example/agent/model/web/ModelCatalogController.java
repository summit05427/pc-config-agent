package com.example.agent.model.web;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.web.dto.ModelSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 模型目录公开接口，供前端模型选择使用。
 */
@RestController
@RequestMapping("/api/v1/models")
@RequiredArgsConstructor
public class ModelCatalogController {

    private final ModelCatalogService modelCatalogService;

    /**
     * @return 当前可用的平台托管模型；纯 BYOK 部署返回空列表
     */
    @GetMapping
    public ApiResponse<List<ModelSummaryResponse>> listModels() {
        List<ModelSummaryResponse> models = modelCatalogService.listAvailable().stream()
                .map(ModelSummaryResponse::from)
                .toList();
        return ApiResponse.success(models);
    }
}
