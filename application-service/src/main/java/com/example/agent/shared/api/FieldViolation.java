package com.example.agent.shared.api;

/**
 * 字段级校验失败项，作为参数错误响应的 {@code data} 返回。
 *
 * @param field   字段名
 * @param message 校验失败原因
 */
public record FieldViolation(String field, String message) {
}
