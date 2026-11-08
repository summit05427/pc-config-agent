package com.example.agent.support;

import com.example.agent.identity.application.AuthAuditEntry;
import com.example.agent.identity.application.AuthAuditLog;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * 测试用内存审计写入，断言认证事件是否按预期产生。
 *
 * <p>生产实现由 {@code MyBatisAuthAuditLog} 提供；没有数据库的集成测试
 * 用它替换，避免 {@code REQUIRES_NEW} 事务去连接真实数据源。</p>
 */
public class InMemoryAuthAuditLog implements AuthAuditLog {

    private final List<AuthAuditEntry> entries = new CopyOnWriteArrayList<>();

    @Override
    public void append(AuthAuditEntry entry) {
        entries.add(entry);
    }

    /**
     * @return 当前累计的审计记录快照
     */
    public List<AuthAuditEntry> findAll() {
        return List.copyOf(entries);
    }

    /** 测试之间共享同一个单例，每个用例开始前需要清空。 */
    public void clear() {
        entries.clear();
    }
}
