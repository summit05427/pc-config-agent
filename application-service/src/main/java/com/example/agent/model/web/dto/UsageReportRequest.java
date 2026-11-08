package com.example.agent.model.web.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 批量上报请求，单批 1..20 条；超过由 Agent 侧拆批，服务端拒绝超大批次以保护数据库。
 *
 * @param records 使用明细
 */
public record UsageReportRequest(
        @NotNull(message = "records 不能为空")
        @Size(min = 1, max = 20, message = "单批 records 数量必须在 1 到 20 之间")
        List<@Valid UsageRecordRequest> records) {
}
