package com.example.agent.model.web;

import com.example.agent.model.application.AdminModelUsageService;
import com.example.agent.model.web.dto.AdminModelUsageItemResponse;
import com.example.agent.model.web.dto.AdminModelUsageQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端用量与成本查询接口。
 *
 * <p>{@code /api/v1/admin/**} 由安全配置统一限制为 {@code ADMIN}，
 * Controller 只负责参数接收与响应组装，过滤、分页与聚合口径全部在服务层与 SQL 中实现。</p>
 */
@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class AdminModelUsageController {

    private final AdminModelUsageService adminModelUsageService;

    @Operation(summary = "分页查询使用明细", description = "跨用户查询；支持用户、Provider、模型、凭证来源、成本状态、结果与日期过滤")
    @GetMapping("/model-usage")
    public ApiResponse<PageResult<AdminModelUsageItemResponse>> listUsage(
            @Valid AdminModelUsageQuery query) {
        return ApiResponse.success(adminModelUsageService.list(query));
    }

    @Operation(summary = "查询用量聚合", description = "请求数、Token、费用与成本状态分布；多币种不求和，金额置空")
    @GetMapping("/model-usage/summary")
    public ApiResponse<AdminModelUsageSummaryResponse> summarizeUsage(
            @Valid AdminModelUsageSummaryQuery query) {
        return ApiResponse.success(adminModelUsageService.summarize(query));
    }
}
