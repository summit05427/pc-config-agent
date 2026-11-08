package com.example.agent.pcbuild.web.dto;

/**
 * 兼容性校验响应。
 *
 * @param valid  是否存在硬冲突（{@code FAIL}）；{@code UNKNOWN} 不影响该值
 * @param report 八条规则报告
 */
public record ValidateResponse(boolean valid, CompatibilityReportResponse report) {
}
