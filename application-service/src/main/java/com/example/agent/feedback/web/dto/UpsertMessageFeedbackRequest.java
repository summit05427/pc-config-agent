package com.example.agent.feedback.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 提交或覆盖一条消息反馈。
 *
 * <p>{@code rating} 与 {@code reasonCode} 的取值校验放在服务层，目的是返回稳定的业务错误码
 * {@code rating_invalid} / {@code reason_invalid}，而不是笼统的参数错误。</p>
 *
 * @param threadId   会话标识，必须与消息所属会话一致
 * @param rating     {@code UP} 或 {@code DOWN}
 * @param reasonCode 踩的原因，点赞时忽略
 * @param comment    用户备注，最多 500 字
 */
public record UpsertMessageFeedbackRequest(
        @NotBlank(message = "threadId 不能为空")
                @Size(max = 64, message = "threadId 不能超过 64 个字符")
                @Pattern(regexp = "^[A-Za-z0-9_.:-]+$", message = "threadId 含有不支持的字符")
                String threadId,
        @NotBlank(message = "rating 不能为空") @Size(max = 8, message = "rating 不能超过 8 个字符") String rating,
        @Size(max = 32, message = "reasonCode 不能超过 32 个字符") String reasonCode,
        @Size(max = 500, message = "备注不能超过 500 个字符") String comment) {
}
