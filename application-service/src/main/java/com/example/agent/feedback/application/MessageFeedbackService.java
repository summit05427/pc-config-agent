package com.example.agent.feedback.application;

import com.example.agent.feedback.domain.FeedbackErrorCode;
import com.example.agent.feedback.domain.FeedbackRating;
import com.example.agent.feedback.domain.FeedbackReason;
import com.example.agent.feedback.infrastructure.AdminFeedbackFilter;
import com.example.agent.feedback.infrastructure.AdminFeedbackRow;
import com.example.agent.feedback.infrastructure.FeedbackRatingCountRow;
import com.example.agent.feedback.infrastructure.MessageFeedbackMapper;
import com.example.agent.feedback.web.dto.AdminFeedbackQuery;
import com.example.agent.feedback.web.dto.AdminFeedbackResponse;
import com.example.agent.feedback.web.dto.FeedbackReasonCount;
import com.example.agent.feedback.web.dto.FeedbackSummaryResponse;
import com.example.agent.feedback.web.dto.MessageFeedbackResponse;
import com.example.agent.feedback.web.dto.UpsertMessageFeedbackRequest;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.regex.Pattern;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 消息反馈服务。
 *
 * <p>归属边界：用户侧所有读写都带 {@code user_id} 条件，只能操作本人反馈；管理端查询走
 * 独立的只读方法，接口层由 {@code SecurityConfig} 的 {@code ADMIN} 规则保护。</p>
 *
 * <p>不在本服务校验消息是否真实存在：Java 不持有对话数据，也不允许调用 Agent。
 * 反馈行归属于提交者本人，未知 {@code message_id} 只会影响统计口径，不会造成越权。</p>
 */
@Service
@RequiredArgsConstructor
public class MessageFeedbackService {

    /** 与 Agent 输出的 message_id 规则一致：{@code {thread_id}:{seq}}，允许字母数字与 . _ : -。 */
    private static final Pattern MESSAGE_ID_PATTERN = Pattern.compile("^[A-Za-z0-9_.:-]{1,128}$");

    private static final Pattern THREAD_ID_PATTERN = Pattern.compile("^[A-Za-z0-9_.:-]{1,64}$");

    /** 导出上限：无筛选时也不把整表读进内存，需要全量时按时间区间分批导出。 */
    private static final int MAX_EXPORT_ROWS = 10_000;

    private static final String CSV_HEADER = "时间,用户,用户ID,会话,消息ID,评分,原因,备注";

    private static final DateTimeFormatter CSV_TIME_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final MessageFeedbackMapper messageFeedbackMapper;

    /**
     * 写入或覆盖本人对一条消息的评价。
     *
     * @param publicId  令牌 {@code sub}
     * @param messageId 路径中的消息标识
     * @param request   已通过 Bean Validation 的请求体
     * @return 写入后的评价
     * @throws BusinessException 标识不合法或评分/原因不在白名单内
     */
    @Transactional
    public MessageFeedbackResponse upsert(
            String publicId, String messageId, UpsertMessageFeedbackRequest request) {
        String normalizedMessageId = requireMessageId(messageId);
        String threadId = requireThreadId(request.threadId());
        FeedbackRating rating = FeedbackRating.from(request.rating());
        // 点赞不记录原因与备注：它们只对「踩」有意义，混入统计会污染原因分布
        FeedbackReason reason = rating == FeedbackRating.DOWN ? FeedbackReason.fromNullable(request.reasonCode()) : null;
        String comment = rating == FeedbackRating.DOWN ? blankToNull(request.comment()) : null;

        messageFeedbackMapper.upsert(
                publicId,
                threadId,
                normalizedMessageId,
                rating.name(),
                reason == null ? null : reason.name(),
                comment);
        return new MessageFeedbackResponse(normalizedMessageId, rating.name(), reason == null ? null : reason.name());
    }

    /**
     * 取消本人对一条消息的评价。
     *
     * @param publicId  令牌 {@code sub}
     * @param messageId 消息标识
     * @throws BusinessException 原本没有反馈时抛 {@link FeedbackErrorCode#FEEDBACK_NOT_FOUND}
     */
    @Transactional
    public void delete(String publicId, String messageId) {
        String normalizedMessageId = requireMessageId(messageId);
        if (messageFeedbackMapper.delete(publicId, normalizedMessageId) == 0) {
            throw new BusinessException(FeedbackErrorCode.FEEDBACK_NOT_FOUND);
        }
    }

    /**
     * 查询本人在一个会话内的全部反馈，用于刷新后恢复高亮。
     *
     * @param publicId 令牌 {@code sub}
     * @param threadId 会话标识
     * @return 反馈列表，按提交时间正序
     */
    @Transactional(readOnly = true)
    public List<MessageFeedbackResponse> listByThread(String publicId, String threadId) {
        return messageFeedbackMapper.findByThread(publicId, requireThreadId(threadId)).stream()
                .map(row -> new MessageFeedbackResponse(row.messageId(), row.rating(), row.reasonCode()))
                .toList();
    }

    /**
     * 管理端分页查询。
     *
     * @param query 筛选与分页参数
     * @return 分页结果
     */
    @Transactional(readOnly = true)
    public PageResult<AdminFeedbackResponse> listForAdmin(AdminFeedbackQuery query) {
        AdminFeedbackFilter filter = toFilter(query);
        long total = messageFeedbackMapper.countPage(filter);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminFeedbackResponse> rows = messageFeedbackMapper
                .selectPage(filter, query.getSize(), query.offset()).stream()
                .map(MessageFeedbackService::toResponse)
                .toList();
        return PageResult.of(rows, total, query);
    }

    /**
     * 管理端统计赞踩总数与踩的原因分布。
     *
     * @param query 筛选参数
     * @return 统计结果
     */
    @Transactional(readOnly = true)
    public FeedbackSummaryResponse summarize(AdminFeedbackQuery query) {
        AdminFeedbackFilter filter = toFilter(query);
        FeedbackRatingCountRow counts = messageFeedbackMapper.countByRating(filter);
        List<FeedbackReasonCount> reasons = messageFeedbackMapper.countByReason(filter).stream()
                .map(row -> {
                    FeedbackReason reason = FeedbackReason.fromNullable(row.reasonCode());
                    return new FeedbackReasonCount(
                            row.reasonCode(), reason == null ? row.reasonCode() : reason.label(), row.total());
                })
                .toList();
        return new FeedbackSummaryResponse(counts.upCount(), counts.downCount(), reasons);
    }

    /**
     * 导出管理端筛选结果。
     *
     * <p>以 UTF-8 BOM 开头，Excel 直接打开中文不乱码；单元格以 {@code '} 前缀防公式注入，
     * 备注来自用户输入，不能原样交给表格软件解释。</p>
     *
     * @param query 筛选参数
     * @return CSV 文本
     */
    @Transactional(readOnly = true)
    public String exportCsv(AdminFeedbackQuery query) {
        AdminFeedbackFilter filter = toFilter(query);
        StringBuilder builder = new StringBuilder("\uFEFF").append(CSV_HEADER).append("\r\n");
        for (AdminFeedbackRow row : messageFeedbackMapper.selectForExport(filter, MAX_EXPORT_ROWS)) {
            builder.append(csvCell(row.createdAt() == null ? "" : row.createdAt().format(CSV_TIME_FORMAT)))
                    .append(',')
                    .append(csvCell(row.username()))
                    .append(',')
                    .append(csvCell(row.userId()))
                    .append(',')
                    .append(csvCell(row.threadId()))
                    .append(',')
                    .append(csvCell(row.messageId()))
                    .append(',')
                    .append(csvCell(ratingLabel(row.rating())))
                    .append(',')
                    .append(csvCell(reasonLabel(row.reasonCode())))
                    .append(',')
                    .append(csvCell(row.comment()))
                    .append("\r\n");
        }
        return builder.toString();
    }

    private static AdminFeedbackFilter toFilter(AdminFeedbackQuery query) {
        return new AdminFeedbackFilter(
                normalizeRating(query.getRating()),
                normalizeReason(query.getReasonCode()),
                blankToNull(query.getUserId()),
                blankToNull(query.getThreadId()),
                fromInclusive(query.getFrom()),
                toExclusive(query.getTo()));
    }

    private static String normalizeRating(String rating) {
        return rating == null || rating.isBlank() ? null : FeedbackRating.from(rating).name();
    }

    private static String normalizeReason(String reasonCode) {
        FeedbackReason reason = FeedbackReason.fromNullable(reasonCode);
        return reason == null ? null : reason.name();
    }

    private static OffsetDateTime fromInclusive(LocalDate from) {
        return from == null ? null : from.atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }

    private static OffsetDateTime toExclusive(LocalDate to) {
        return to == null ? null : to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }

    private static String requireMessageId(String messageId) {
        String normalized = messageId == null ? "" : messageId.trim();
        if (!MESSAGE_ID_PATTERN.matcher(normalized).matches()) {
            throw new BusinessException(FeedbackErrorCode.MESSAGE_ID_INVALID);
        }
        return normalized;
    }

    private static String requireThreadId(String threadId) {
        String normalized = threadId == null ? "" : threadId.trim();
        if (!THREAD_ID_PATTERN.matcher(normalized).matches()) {
            throw new BusinessException(FeedbackErrorCode.THREAD_ID_INVALID);
        }
        return normalized;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static AdminFeedbackResponse toResponse(AdminFeedbackRow row) {
        return new AdminFeedbackResponse(
                row.userId(),
                row.username(),
                row.threadId(),
                row.messageId(),
                row.rating(),
                row.reasonCode(),
                row.comment(),
                row.createdAt());
    }

    private static String ratingLabel(String rating) {
        return FeedbackRating.UP.name().equals(rating) ? "赞" : "踩";
    }

    private static String reasonLabel(String reasonCode) {
        FeedbackReason reason = FeedbackReason.fromNullable(reasonCode);
        return reason == null ? "" : reason.label();
    }

    private static String csvCell(String value) {
        if (value == null || value.isEmpty()) {
            return "";
        }
        String guarded = isFormulaRisk(value) ? "'" + value : value;
        return "\"" + guarded.replace("\"", "\"\"") + "\"";
    }

    private static boolean isFormulaRisk(String value) {
        char first = value.charAt(0);
        return first == '=' || first == '+' || first == '-' || first == '@';
    }
}
