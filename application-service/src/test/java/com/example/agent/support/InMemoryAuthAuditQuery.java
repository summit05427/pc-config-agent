package com.example.agent.support;

import com.example.agent.identity.application.AuthAuditQuery;
import com.example.agent.identity.domain.AuthAuditLogItem;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 测试用内存审计查询，供管理端审计列表接口断言过滤与分页。
 *
 * <p>与 {@link InMemoryAuthAuditLog} 分开：后者只验证「业务动作是否写入审计」，
 * 本类只负责「查询侧读到什么」，两者共用同一张表在生产中并不共用端口。</p>
 */
public class InMemoryAuthAuditQuery implements AuthAuditQuery {

    private final AtomicLong sequence = new AtomicLong();
    private final List<Entry> entries = new CopyOnWriteArrayList<>();

    /**
     * 预置一条审计记录。
     *
     * @param event     事件标识
     * @param username  登录名
     * @param ip        客户端 IP，可为 {@code null}
     * @param createdAt 发生时间
     */
    public void add(String event, String username, String ip, Instant createdAt) {
        entries.add(new Entry(sequence.incrementAndGet(), new AuthAuditLogItem(event, username, ip, createdAt)));
    }

    /** 测试之间共享同一个单例，每个用例开始前需要清空。 */
    public void clear() {
        entries.clear();
        sequence.set(0);
    }

    @Override
    public long count(String event, String username) {
        return filtered(event, username).size();
    }

    @Override
    public List<AuthAuditLogItem> findPage(String event, String username, long offset, int size) {
        return filtered(event, username).stream()
                .sorted(Comparator.comparing((Entry entry) -> entry.item().createdAt())
                        .thenComparingLong(Entry::sequence)
                        .reversed())
                .skip(offset)
                .limit(size)
                .map(Entry::item)
                .toList();
    }

    private List<Entry> filtered(String event, String username) {
        return entries.stream()
                .filter(entry -> event == null || entry.item().event().equals(event))
                .filter(entry -> username == null || entry.item().username().equals(username))
                .toList();
    }

    private record Entry(long sequence, AuthAuditLogItem item) {
    }
}
