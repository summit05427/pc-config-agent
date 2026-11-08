package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.LocalDate;

/**
 * 报价响应。
 *
 * <p>{@code priceFen} 单位为人民币分；{@code priceSource} 与 {@code verifiedPrice}
 * 用于区分人工核验价与演示价，调用方不得只看金额。</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record OfferResponse(
        String offerId,
        String hardwareId,
        HardwareCategory category,
        String platform,
        String seller,
        String shopName,
        String title,
        String platformSku,
        long priceFen,
        String priceType,
        String purchaseUrl,
        LocalDate verifiedAt,
        LocalDate validUntil,
        String matchStatus,
        String priceSource,
        boolean verifiedPrice,
        String notes) {

    /**
     * @param offer 领域报价
     * @return 响应
     */
    public static OfferResponse from(Offer offer) {
        return new OfferResponse(
                offer.offerId(),
                offer.hardwareId(),
                offer.category(),
                offer.platform(),
                offer.seller(),
                offer.shopName(),
                offer.title(),
                offer.platformSku(),
                offer.priceFen(),
                offer.priceType(),
                offer.purchaseUrl(),
                offer.verifiedAt(),
                offer.validUntil(),
                offer.matchStatus(),
                offer.priceSource(),
                offer.isVerifiedPrice(),
                offer.notes());
    }
}
