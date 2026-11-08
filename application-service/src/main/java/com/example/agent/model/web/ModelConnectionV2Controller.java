package com.example.agent.model.web;

import com.example.agent.model.application.ProviderConnectionService;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.web.dto.ModelConnectionResponse;
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
 * BYOK 连接分页接口（v2）。
 *
 * <p>只有列表读取是破坏性变更：v1 {@code /api/v1/model-connections} 返回全量数组，
 * 创建、验证、删除仍由 v1 提供，避免同一写操作出现两套入口。</p>
 */
@RestController
@RequestMapping("/api/v2/model-connections")
@RequiredArgsConstructor
public class ModelConnectionV2Controller {

    private final ProviderConnectionService providerConnectionService;

    /**
     * @param pageQuery      分页参数，默认第 1 页、每页 20 条，最大 100
     * @param authentication 当前登录用户
     * @return 当前页连接视图与总数，只含掩码与状态
     */
    @Operation(summary = "分页查询模型连接", description = "按令牌归属返回 ACTIVE 连接，只含掩码与状态")
    @GetMapping
    public ApiResponse<PageResult<ModelConnectionResponse>> list(
            @Valid PageQuery pageQuery,
            Authentication authentication) {
        PageResult<ProviderConnectionView> page = providerConnectionService
                .list(CurrentUser.id(authentication), pageQuery);
        List<ModelConnectionResponse> list = page.list().stream()
                .map(ModelConnectionResponse::from)
                .toList();
        return ApiResponse.success(new PageResult<>(list, page.total(), page.page(), page.size()));
    }
}
