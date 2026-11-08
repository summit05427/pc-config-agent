package com.example.agent.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.QuotaExceededDetail;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.web.GlobalExceptionHandler;
import com.example.agent.shared.web.RequestIdFilter;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 信封 {@code errorType} 契约：只在错误响应出现，且位于顶层而不是 {@code data}。
 *
 * <p>把标识放进 {@code data} 会让调用方无法区分「渲染数据」与「弹窗报错」——
 * 错误时 {@code data} 通常为空，混入字段会让前端状态机判断变复杂。</p>
 */
class ApiResponseErrorTypeTests {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(new TestController())
                .setControllerAdvice(new GlobalExceptionHandler())
                .addFilters(new RequestIdFilter())
                .build();
    }

    @Test
    void successResponseShouldNotContainErrorType() throws Exception {
        mockMvc.perform(get("/test/ok"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.errorType").doesNotExist());
    }

    @Test
    void businessErrorShouldExposeErrorTypeAtTopLevel() throws Exception {
        mockMvc.perform(get("/test/quota"))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code").value(ModelErrorCode.QUOTA_EXCEEDED.code()))
                .andExpect(jsonPath("$.errorType").value("quota_exceeded"))
                // 结构化错误详情走 data，但 errorType 不在 data 内部
                .andExpect(jsonPath("$.data.quotaType").value("daily_requests"))
                .andExpect(jsonPath("$.data.resetAt").isNotEmpty())
                .andExpect(jsonPath("$.data.errorType").doesNotExist());
    }

    @RestController
    @RequestMapping("/test")
    static class TestController {

        @GetMapping("/ok")
        ApiResponse<String> ok() {
            return ApiResponse.success("hello");
        }

        @GetMapping("/quota")
        ApiResponse<Void> quota() {
            throw new BusinessException(
                    ModelErrorCode.QUOTA_EXCEEDED,
                    ModelErrorCode.QUOTA_EXCEEDED.message(),
                    new QuotaExceededDetail(
                            "daily_requests", 100, 100, OffsetDateTime.parse("2026-10-31T00:00:00Z")));
        }
    }
}
