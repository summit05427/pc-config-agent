package com.example.agent.pcbuild.web.dto;

import java.util.List;

/**
 * 报价列表。
 *
 * @param dataStatus         报价集合状态，{@code MIXED_DEMO} 表示同时包含核验价与演示价
 * @param priceUnit          价格单位，固定 {@code CNY_FEN}
 * @param verifiedOfferCount 人工核验价条数
 * @param mockOfferCount     演示价条数
 * @param total              本次返回条数
 * @param list               数据
 */
public record OfferListResponse(
        String dataStatus,
        String priceUnit,
        long verifiedOfferCount,
        long mockOfferCount,
        int total,
        List<OfferResponse> list) {
}
