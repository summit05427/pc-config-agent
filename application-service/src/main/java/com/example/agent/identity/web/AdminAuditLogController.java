package com.example.agent.identity.web;

import com.example.agent.identity.application.AdminAuditLogService;
import com.example.agent.identity.web.dto.AdminAuditLogListQuery;
import com.example.agent.identity.web.dto.AdminAuditLogResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端认证审计查询接口。
 *
 * <p>只读；鉴权由 {@code /api/v1/admin/**} 的 {@code ADMIN} 规则统一完成。</p>
 */
@RestController
@RequestMapping("/api/v1/admin/audit-logs")
@RequiredArgsConstructor
public class AdminAuditLogController {

    private final AdminAuditLogService adminAuditLogService;

    @Operation(summary = "分页查询认证审计", description = "支持事件与登录名过滤，按发生时间倒序；不含 User-Agent 与请求 ID")
    @GetMapping
    public ApiResponse<PageResult<AdminAuditLogResponse>> listAuditLogs(
            @Valid AdminAuditLogListQuery query) {
        return ApiResponse.success(adminAuditLogService.listAuditLogs(query));
    }
}
