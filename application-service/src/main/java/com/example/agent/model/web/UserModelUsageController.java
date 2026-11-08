package com.example.agent.model.web;

import com.example.agent.model.application.ModelUsageQueryService;
import com.example.agent.model.web.dto.ModelUsageResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.security.CurrentUser;
import io.swagger.v3.oas.annotations.Operation;
import java.time.LocalDate;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 本人模型用量查询接口。
 *
 * <p>固定路径 {@code /users/me/model-usage}，用户身份只取令牌 {@code sub}，
 * 不提供按用户 ID 查询的入口，天然不存在越权路径。</p>
 */
@RestController
@RequestMapping("/api/v1/users/me/model-usage")
@RequiredArgsConstructor
public class UserModelUsageController {

    private final ModelUsageQueryService modelUsageQueryService;

    /**
     * @param page 页码，默认 1
     * @param size 每页条数，默认 20，最大 100
     * @param from 起始日期（ISO-8601，UTC 自然日），可选
     * @param to   截止日期（ISO-8601，UTC 自然日），可选
     * @param authentication 当前登录用户
     * @return 当日额度快照与使用明细分页
     */
    @Operation(summary = "查询本人模型用量", description = "返回当日额度与本人使用明细，不返回他人数据")
    @GetMapping
    public ApiResponse<ModelUsageResponse> query(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
            Authentication authentication) {
        return ApiResponse.success(ModelUsageResponse.from(
                modelUsageQueryService.query(CurrentUser.id(authentication), from, to, page, size)));
    }
}
