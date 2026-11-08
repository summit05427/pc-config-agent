package com.example.agent.api;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import com.example.agent.shared.web.GlobalExceptionHandler;
import com.example.agent.shared.web.RequestIdFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 公共 API 契约测试，不启动 Spring 容器，直接验证响应结构、错误映射与请求 ID。
 */
class PublicApiContractTests {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        mockMvc = MockMvcBuilders.standaloneSetup(new TestController())
                .setControllerAdvice(new GlobalExceptionHandler())
                .setValidator(validator)
                .addFilters(new RequestIdFilter())
                .build();
    }

    @Test
    void successResponseContainsEnvelopeAndRequestId() throws Exception {
        mockMvc.perform(get("/test/ok"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.message").value("ok"))
                .andExpect(jsonPath("$.data").value("hello"))
                .andExpect(jsonPath("$.requestId").isNotEmpty());
    }

    @Test
    void requestIdFromHeaderIsReused() throws Exception {
        mockMvc.perform(get("/test/ok").header(RequestIdFilter.REQUEST_ID_HEADER, "trace-123"))
                .andExpect(status().isOk())
                .andExpect(header().string(RequestIdFilter.REQUEST_ID_HEADER, "trace-123"))
                .andExpect(jsonPath("$.requestId").value("trace-123"));
    }

    @Test
    void paginationDefaultsAreApplied() throws Exception {
        mockMvc.perform(get("/test/paged"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.page").value(PageQuery.DEFAULT_PAGE))
                .andExpect(jsonPath("$.data.size").value(PageQuery.DEFAULT_SIZE))
                .andExpect(jsonPath("$.data.total").value(1));
    }

    @Test
    void pageSizeOverLimitIsRejected() throws Exception {
        mockMvc.perform(get("/test/paged").param("size", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.PARAM_INVALID.code()))
                .andExpect(jsonPath("$.data[0].field").value("size"))
                .andExpect(jsonPath("$.data[0].message").value(containsString("100")));
    }

    @Test
    void methodParameterConstraintIsMappedTo400() throws Exception {
        mockMvc.perform(get("/test/size-limit").param("size", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.PARAM_INVALID.code()))
                .andExpect(jsonPath("$.data[0].field").value(containsString("size")));
    }

    @Test
    void businessExceptionMapsToErrorCodeAndStatus() throws Exception {
        mockMvc.perform(get("/test/business-error"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.BUSINESS_ERROR.code()))
                .andExpect(jsonPath("$.message").value("余额不足"));
    }

    @Test
    void missingParameterMapsToBadRequest() throws Exception {
        mockMvc.perform(get("/test/required"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.PARAM_MISSING.code()))
                .andExpect(jsonPath("$.message").value(containsString("name")));
    }

    @Test
    void methodNotAllowedMapsTo405() throws Exception {
        mockMvc.perform(post("/test/ok"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.METHOD_NOT_ALLOWED.code()));
    }

    @Test
    void systemExceptionHidesInternalDetail() throws Exception {
        mockMvc.perform(get("/test/system-error"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value(CommonErrorCode.SYSTEM_ERROR.code()))
                .andExpect(jsonPath("$.message").value(CommonErrorCode.SYSTEM_ERROR.message()))
                .andExpect(content().string(not(containsString("password=secret"))))
                .andExpect(content().string(not(containsString("IllegalStateException"))));
    }

    @RestController
    @RequestMapping("/test")
    static class TestController {

        @GetMapping("/ok")
        ApiResponse<String> ok() {
            return ApiResponse.success("hello");
        }

        @GetMapping("/paged")
        ApiResponse<PageResult<String>> paged(@Valid PageQuery query) {
            return ApiResponse.success(PageResult.of(List.of("item"), 1, query));
        }

        @GetMapping("/required")
        ApiResponse<String> required(@RequestParam String name) {
            return ApiResponse.success(name);
        }

        @GetMapping("/size-limit")
        ApiResponse<Integer> sizeLimit(@RequestParam @Min(1) @Max(100) int size) {
            return ApiResponse.success(size);
        }

        @GetMapping("/business-error")
        ApiResponse<Void> businessError() {
            throw new BusinessException(CommonErrorCode.BUSINESS_ERROR, "余额不足");
        }

        @GetMapping("/system-error")
        ApiResponse<Void> systemError() {
            throw new IllegalStateException("数据库连接失败, password=secret");
        }
    }
}
