package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.AuthAuditEntry;
import com.example.agent.identity.application.AuthAuditLog;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 认证审计的数据库实现。
 *
 * <p>使用 {@code REQUIRES_NEW}：认证失败会以异常结束业务流程，若与业务共用事务，
 * 审计记录会随业务回滚一起丢失。独立事务能保证「失败事件」同样落库，
 * 也让审计写入不延长业务事务的持锁时间。</p>
 */
@Component
@RequiredArgsConstructor
public class MyBatisAuthAuditLog implements AuthAuditLog {

    private final AuthAuditLogMapper authAuditLogMapper;

    @Override
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void append(AuthAuditEntry entry) {
        authAuditLogMapper.insert(
                entry.username(),
                entry.publicId(),
                entry.event().value(),
                entry.ip(),
                entry.userAgent(),
                entry.requestId());
    }
}
