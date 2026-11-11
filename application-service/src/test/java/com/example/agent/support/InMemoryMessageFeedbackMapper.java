package com.example.agent.support;

import com.example.agent.feedback.infrastructure.AdminFeedbackFilter;
import com.example.agent.feedback.infrastructure.AdminFeedbackRow;
import com.example.agent.feedback.infrastructure.FeedbackRatingCountRow;
import com.example.agent.feedback.infrastructure.FeedbackReasonCountRow;
import com.example.agent.feedback.infrastructure.MessageFeedbackMapper;
import com.example.agent.feedback.infrastructure.MessageFeedbackRow;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 内存反馈持久化，供接口测试断言归属、覆盖、筛选与导出。
 *
 * <p>生产实现是 MyBatis 适配器；这里保持同一套语义（唯一键 {@code (user_id, message_id)}、
 * 点赞不落原因、时间倒序），差异只在存储介质。用户名通过 {@link #registerUsername} 预置，
 * 模拟管理端 SQL 的 {@code LEFT JOIN users}。</p>
 */
public class InMemoryMessageFeedbackMapper implements MessageFeedbackMapper {

    private final AtomicLong sequence = new AtomicLong();

    private final Map<String, Entry> entries = new LinkedHashMap<>();

    private final Map<String, String> usernames = new LinkedHashMap<>();

    /**
     * 预置公开 ID 与登录名的映射。
     *
     * @param publicId 用户公开 ID
     * @param username 登录名或昵称
     */
    public void registerUsername(String publicId, String username) {
        usernames.put(publicId, username);
    }

    /** 测试之间共享同一个单例，每个用例开始前需要清空。 */
    public void clear() {
        entries.clear();
        usernames.clear();
        sequence.set(0);
    }

    @Override
    public int upsert(
            String userId,
            String threadId,
            String messageId,
            String rating,
            String reasonCode,
            String comment) {
        String key = key(userId, messageId);
        Entry existing = entries.get(key);
        OffsetDateTime createdAt = existing == null ? now() : existing.createdAt();
        entries.put(
                key,
                new Entry(sequence.incrementAndGet(), userId, threadId, messageId, rating, reasonCode, comment, createdAt));
        return 1;
    }

    @Override
    public int delete(String userId, String messageId) {
        return entries.remove(key(userId, messageId)) == null ? 0 : 1;
    }

    @Override
    public List<MessageFeedbackRow> findByThread(String userId, String threadId) {
        return entries.values().stream()
                .filter(entry -> entry.userId().equals(userId) && entry.threadId().equals(threadId))
                .sorted(Comparator.comparing(Entry::createdAt).thenComparingLong(Entry::sequence))
                .map(entry -> new MessageFeedbackRow(entry.messageId(), entry.rating(), entry.reasonCode()))
                .toList();
    }

    @Override
    public long countPage(AdminFeedbackFilter filter) {
        return filtered(filter).size();
    }

    @Override
    public List<AdminFeedbackRow> selectPage(AdminFeedbackFilter filter, int size, long offset) {
        return filtered(filter).stream()
                .sorted(Comparator.comparing(Entry::createdAt).thenComparingLong(Entry::sequence).reversed())
                .skip(offset)
                .limit(size)
                .map(this::toAdminRow)
                .toList();
    }

    @Override
    public FeedbackRatingCountRow countByRating(AdminFeedbackFilter filter) {
        List<Entry> matched = filtered(filter);
        long up = matched.stream().filter(entry -> "UP".equals(entry.rating())).count();
        long down = matched.stream().filter(entry -> "DOWN".equals(entry.rating())).count();
        return new FeedbackRatingCountRow(up, down);
    }

    @Override
    public List<FeedbackReasonCountRow> countByReason(AdminFeedbackFilter filter) {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (Entry entry : filtered(filter)) {
            if ("DOWN".equals(entry.rating()) && entry.reasonCode() != null) {
                counts.merge(entry.reasonCode(), 1L, Long::sum);
            }
        }
        return counts.entrySet().stream()
                .map(item -> new FeedbackReasonCountRow(item.getKey(), item.getValue()))
                .sorted(Comparator.comparingLong(FeedbackReasonCountRow::total).reversed()
                        .thenComparing(FeedbackReasonCountRow::reasonCode))
                .toList();
    }

    @Override
    public List<AdminFeedbackRow> selectForExport(AdminFeedbackFilter filter, int limit) {
        return filtered(filter).stream()
                .sorted(Comparator.comparing(Entry::createdAt).thenComparingLong(Entry::sequence).reversed())
                .limit(limit)
                .map(this::toAdminRow)
                .toList();
    }

    private List<Entry> filtered(AdminFeedbackFilter filter) {
        return entries.values().stream().filter(entry -> matches(entry, filter)).toList();
    }

    private static boolean matches(Entry entry, AdminFeedbackFilter filter) {
        return (filter.rating() == null || filter.rating().equals(entry.rating()))
                && (filter.reasonCode() == null || filter.reasonCode().equals(entry.reasonCode()))
                && (filter.userId() == null || filter.userId().equalsIgnoreCase(entry.userId()))
                && (filter.threadId() == null || filter.threadId().equals(entry.threadId()))
                && (filter.fromInclusive() == null || !entry.createdAt().isBefore(filter.fromInclusive()))
                && (filter.toExclusive() == null || entry.createdAt().isBefore(filter.toExclusive()));
    }

    private AdminFeedbackRow toAdminRow(Entry entry) {
        return new AdminFeedbackRow(
                entry.userId(),
                usernames.get(entry.userId()),
                entry.threadId(),
                entry.messageId(),
                entry.rating(),
                entry.reasonCode(),
                entry.comment(),
                entry.createdAt());
    }

    private static String key(String userId, String messageId) {
        return userId + "|" + messageId;
    }

    private static OffsetDateTime now() {
        return OffsetDateTime.now(ZoneOffset.UTC);
    }

    private record Entry(
            long sequence,
            String userId,
            String threadId,
            String messageId,
            String rating,
            String reasonCode,
            String comment,
            OffsetDateTime createdAt) {
    }
}
