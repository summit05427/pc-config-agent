package com.example.agent.model.web.dto;

import com.example.agent.model.domain.UsageReportResult;

/**
 * 批量上报结果。
 *
 * @param accepted   新入库条数
 * @param duplicated 幂等命中的条数
 * @param rejected   校验未通过的条数
 */
public record UsageReportResponse(int accepted, int duplicated, int rejected) {

    /**
     * @param result 服务层结果
     * @return 对外响应
     */
    public static UsageReportResponse from(UsageReportResult result) {
        return new UsageReportResponse(result.accepted(), result.duplicated(), result.rejected());
    }
}
