package com.example.agent.feedback.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import lombok.Getter;
import lombok.Setter;
import org.springframework.format.annotation.DateTimeFormat;

/**
 * 管理端反馈查询参数。
 *
 * <p>空串表示不过滤。{@code rating} 与 {@code reasonCode} 的白名单必须与
 * {@code FeedbackRating} / {@code FeedbackReason} 保持一致。</p>
 */
@Getter
@Setter
public class AdminFeedbackQuery extends PageQuery {

    public static final String RATING_PATTERN = "^$|UP|DOWN";

    public static final String REASON_PATTERN = "^$|INACCURATE|OFF_TOPIC|INCOMPLETE|FORMAT|UNSAFE|OTHER";

    public static final String USER_ID_PATTERN =
            "^$|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

    @Pattern(regexp = RATING_PATTERN, message = "rating 只能是 UP 或 DOWN")
    private String rating;

    @Pattern(
            regexp = REASON_PATTERN,
            message = "reasonCode 只能是 INACCURATE、OFF_TOPIC、INCOMPLETE、FORMAT、UNSAFE、OTHER")
    private String reasonCode;

    @Pattern(regexp = USER_ID_PATTERN, message = "userId 必须是 UUID")
    private String userId;

    @Size(max = 64, message = "threadId 不能超过 64 个字符")
    private String threadId;

    /** 起始日期（含），按 UTC 零点解析。 */
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    /** 结束日期（含），查询时转换为次日零点（不含）。 */
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate to;
}
