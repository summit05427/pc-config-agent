package com.example.agent.feedback.web;

import com.example.agent.feedback.application.MessageFeedbackService;
import com.example.agent.feedback.web.dto.AdminFeedbackQuery;
import com.example.agent.feedback.web.dto.AdminFeedbackResponse;
import com.example.agent.feedback.web.dto.FeedbackSummaryResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageResult;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端反馈接口。
 *
 * <p>路径位于 {@code /api/v1/admin/**}，由 {@code SecurityConfig} 统一要求 {@code ADMIN} 角色，
 * 本类不再重复鉴权判断。</p>
 */
@RestController
@RequestMapping("/api/v1/admin/feedback")
@RequiredArgsConstructor
public class AdminFeedbackController {

    private static final DateTimeFormatter FILE_TIME_FORMAT = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final MessageFeedbackService messageFeedbackService;

    @Operation(summary = "反馈列表", description = "按评分、原因、用户、会话与日期区间筛选，按提交时间倒序分页")
    @GetMapping
    public ApiResponse<PageResult<AdminFeedbackResponse>> list(@Valid AdminFeedbackQuery query) {
        return ApiResponse.success(messageFeedbackService.listForAdmin(query));
    }

    @Operation(summary = "反馈统计", description = "返回赞踩总数与踩的原因分布，筛选口径与列表一致")
    @GetMapping("/summary")
    public ApiResponse<FeedbackSummaryResponse> summary(@Valid AdminFeedbackQuery query) {
        return ApiResponse.success(messageFeedbackService.summarize(query));
    }

    @Operation(summary = "导出反馈 CSV", description = "按当前筛选条件导出，最多 10000 行，UTF-8 BOM 便于 Excel 直接打开")
    @GetMapping("/export")
    public ResponseEntity<byte[]> export(@Valid AdminFeedbackQuery query) {
        byte[] body = messageFeedbackService.exportCsv(query).getBytes(StandardCharsets.UTF_8);
        String filename = "feedback-" + OffsetDateTime.now().format(FILE_TIME_FORMAT) + ".csv";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(new MediaType("text", "csv", StandardCharsets.UTF_8));
        headers.setContentDisposition(
                ContentDisposition.attachment().filename(filename, StandardCharsets.UTF_8).build());
        return ResponseEntity.ok().headers(headers).body(body);
    }
}
