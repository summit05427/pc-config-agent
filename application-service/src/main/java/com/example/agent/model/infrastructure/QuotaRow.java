package com.example.agent.model.infrastructure;

/**
 * 额度行。
 *
 * <p>字段用包装类型：MyBatis 按构造器映射结果时只认 {@code java.lang.Integer} 这类
 * 可解析的 javaType，原始 {@code int} 找不到对应类型处理器。</p>
 *
 * @param usedCount  已用数量
 * @param limitCount 当日上限快照
 */
public record QuotaRow(Integer usedCount, Integer limitCount) {
}
