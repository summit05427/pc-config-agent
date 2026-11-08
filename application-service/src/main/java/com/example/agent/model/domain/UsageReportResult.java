package com.example.agent.model.domain;

/**
 * 批量上报结果。
 *
 * @param accepted   新入库条数
 * @param duplicated 幂等命中的条数（已存在，不重复写库与计费）
 * @param rejected   校验未通过条数（任务不存在、归属或字段不一致）
 */
public record UsageReportResult(int accepted, int duplicated, int rejected) {
}
