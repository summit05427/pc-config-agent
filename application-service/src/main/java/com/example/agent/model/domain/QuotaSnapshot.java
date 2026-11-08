package com.example.agent.model.domain;

/**
 * 每日请求额度快照。
 *
 * <p>字段保持包装类型：底层结果集可能为 {@code null}，在 application 组装错误详情时再判空。</p>
 *
 * @param usedCount  已用数量
 * @param limitCount 当日上限快照
 */
public record QuotaSnapshot(Integer usedCount, Integer limitCount) {
}
