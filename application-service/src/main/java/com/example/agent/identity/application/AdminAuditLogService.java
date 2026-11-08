package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditLogItem;
import com.example.agent.identity.web.dto.AdminAuditLogListQuery;
import com.example.agent.identity.web.dto.AdminAuditLogResponse;
import com.example.agent.shared.api.PageResult;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 管理端审计查询服务。
 *
 * <p>只读且不落任何敏感字段：返回事件、登录名、IP 与时间，
 * User-Agent 与请求 ID 仅保留在库中供服务端排查。</p>
 */
@Service
@RequiredArgsConstructor
public class AdminAuditLogService {

    private final AuthAuditQuery authAuditQuery;

    /**
     * 按事件与登录名过滤审计记录，按发生时间倒序分页。
     *
     * @param query 查询参数
     * @return 分页结果
     */
    @Transactional(readOnly = true)
    public PageResult<AdminAuditLogResponse> listAuditLogs(AdminAuditLogListQuery query) {
        String event = blankToNull(query.getEvent());
        String username = blankToNull(query.getUsername());
        long total = authAuditQuery.count(event, username);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminAuditLogResponse> logs = authAuditQuery
                .findPage(event, username, query.offset(), query.getSize()).stream()
                .map(AdminAuditLogService::toResponse)
                .toList();
        return PageResult.of(logs, total, query);
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static AdminAuditLogResponse toResponse(AuthAuditLogItem item) {
        return new AdminAuditLogResponse(item.event(), item.username(), item.ip(), item.createdAt());
    }
}
