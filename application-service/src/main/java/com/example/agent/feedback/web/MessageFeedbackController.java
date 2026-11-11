package com.example.agent.feedback.web;

import com.example.agent.feedback.application.MessageFeedbackService;
import com.example.agent.feedback.web.dto.MessageFeedbackResponse;
import com.example.agent.feedback.web.dto.UpsertMessageFeedbackRequest;
import com.example.agent.shared.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 用户侧消息反馈接口。
 *
 * <p>用 PUT 而不是 POST：同一条消息的评价是幂等覆盖，重复提交不会产生多条记录。</p>
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class MessageFeedbackController {

    private final MessageFeedbackService messageFeedbackService;

    @Operation(summary = "提交或覆盖消息反馈", description = "同一用户对同一条消息只保留一条评价，重复提交即覆盖")
    @PutMapping("/messages/{messageId}/feedback")
    public ApiResponse<MessageFeedbackResponse> upsert(
            @PathVariable String messageId,
            @Valid @RequestBody UpsertMessageFeedbackRequest request,
            Authentication authentication) {
        return ApiResponse.success(messageFeedbackService.upsert(authentication.getName(), messageId, request));
    }

    @Operation(summary = "取消消息反馈", description = "删除本人对指定消息的评价")
    @DeleteMapping("/messages/{messageId}/feedback")
    public ApiResponse<Void> delete(@PathVariable String messageId, Authentication authentication) {
        messageFeedbackService.delete(authentication.getName(), messageId);
        return ApiResponse.success();
    }

    @Operation(summary = "查询本人会话反馈", description = "返回该会话下本人提交过的全部评价，用于刷新后恢复高亮")
    @GetMapping("/feedback")
    public ApiResponse<List<MessageFeedbackResponse>> list(
            @RequestParam String threadId, Authentication authentication) {
        return ApiResponse.success(messageFeedbackService.listByThread(authentication.getName(), threadId));
    }
}
