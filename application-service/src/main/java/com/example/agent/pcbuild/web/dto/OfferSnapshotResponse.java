package com.example.agent.pcbuild.web.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/**
 * 快照中的报价集合，保留数据状态与价格单位。
 *
 * @param dataStatus 报价集合状态
 * @param priceUnit  价格单位
 * @param offers     报价
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record OfferSnapshotResponse(
        String dataStatus,
        String priceUnit,
        List<OfferResponse> offers) {
}
