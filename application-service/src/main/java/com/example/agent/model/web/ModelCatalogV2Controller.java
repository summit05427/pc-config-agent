package com.example.agent.model.web;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.web.dto.ModelSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.security.CurrentUser;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 模型目录分页接口（v2）。
 *
 * <p>v1 的 {@code /api/v1/models} 返回全量数组，随目录增长不再符合分页契约；
 * v2 只负责分页读取，保持向后兼容，v1 不删除。</p>
 */
@RestController
@RequestMapping("/api/v2/models")
@RequiredArgsConstructor
public class ModelCatalogV2Controller {

    private final ModelCatalogService modelCatalogService;

    /**
     * @param pageQuery 分页参数，默认第 1 页、每页 20 条，最大 100
     * @return 当前页模型与总数；运行时未启用时返回 404
     */
    @Operation(
            summary = "分页查询可用模型",
            description = "返回当前用户可见的模型：平台托管模型 + 已接入 Provider 的 BYOK 模型；"
                    + "size 超过 100 返回 400")
    @GetMapping
    public ApiResponse<PageResult<ModelSummaryResponse>> listModels(
            @Valid PageQuery pageQuery, Authentication authentication) {
        PageResult<ResolvedModel> page = modelCatalogService.listAvailable(
                pageQuery, CurrentUser.id(authentication));
        List<ModelSummaryResponse> list = page.list().stream()
                .map(ModelSummaryResponse::from)
                .toList();
        return ApiResponse.success(new PageResult<>(list, page.total(), page.page(), page.size()));
    }
}
