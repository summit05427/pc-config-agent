package com.example.agent.model.domain;

import java.time.OffsetDateTime;

/**
 * 额度错误的结构化信息，随 429 响应返回，供 Agent 组装面向浏览器的错误体。
 *
 * @param quotaType 额度类型，首版固定 {@code daily_requests}
 * @param limit     当日上限（写入当日快照）
 * @param used      已用数量
 * @param resetAt   重置时间（次日 00:00:00Z）
 */
public record QuotaExceededDetail(String quotaType, int limit, int used, OffsetDateTime resetAt) {
}
