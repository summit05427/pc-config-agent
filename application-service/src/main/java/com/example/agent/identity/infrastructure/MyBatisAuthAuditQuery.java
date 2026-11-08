package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.AuthAuditQuery;
import com.example.agent.identity.domain.AuthAuditLogItem;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * PostgreSQL 审计查询实现。
 *
 * <p>读取与写入共用同一张表但不共用端口：写入要求独立事务与容错，
 * 查询是管理端的同步只读操作，失败应当直接暴露给调用方。</p>
 */
@Component
@RequiredArgsConstructor
public class MyBatisAuthAuditQuery implements AuthAuditQuery {

    private final AuthAuditLogMapper authAuditLogMapper;

    @Override
    public long count(String event, String username) {
        return authAuditLogMapper.countPage(event, username);
    }

    @Override
    public List<AuthAuditLogItem> findPage(String event, String username, long offset, int size) {
        return authAuditLogMapper.selectPage(event, username, offset, size).stream()
                .map(row -> new AuthAuditLogItem(row.getEvent(), row.getUsername(), row.getIp(), row.getCreatedAt()))
                .toList();
    }
}
