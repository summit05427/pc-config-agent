package com.example.agent.model.web;

import com.example.agent.model.application.AdminModelConnectionService;
import com.example.agent.model.web.dto.AdminModelConnectionQuery;
import com.example.agent.model.web.dto.AdminModelConnectionResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端模型连接只读接口。
 *
 * <p>只提供查询：管理端不得修改用户连接或凭证；响应只含掩码与验证时间。</p>
 */
@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class AdminModelConnectionController {

    private final AdminModelConnectionService adminModelConnectionService;

    @Operation(summary = "分页查询模型连接", description = "只读；返回凭证掩码与最近验证时间，不返回密文或明文")
    @GetMapping("/model-connections")
    public ApiResponse<PageResult<AdminModelConnectionResponse>> listConnections(
            @Valid AdminModelConnectionQuery query) {
        return ApiResponse.success(adminModelConnectionService.list(query));
    }
}
