package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildComponent;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.LocalDate;

/**
 * 方案中的单个硬件条目。
 *
 * <p>{@code priceFen} 单位人民币分；{@code priceSource}/{@code verifiedPrice}
 * 用于说明该价格是否已核验。</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record BuildComponentResponse(
        HardwareCategory category,
        String hardwareId,
        String brand,
        String modelName,
        String specSummary,
        String title,
        long priceFen,
        String priceSource,
        String priceType,
        boolean verifiedPrice,
        String purchaseUrl,
        String platform,
        String seller,
        String offerId,
        String matchStatus,
        LocalDate verifiedAt,
        LocalDate validUntil,
        String benchmarkType,
        Double benchmarkScore) {

    /**
     * @param component 领域条目
     * @return 响应
     */
    public static BuildComponentResponse from(BuildComponent component) {
        Hardware hardware = component.hardware();
        Offer offer = component.offer();
        return new BuildComponentResponse(
                hardware.category(),
                hardware.hardwareId(),
                hardware.brand(),
                hardware.modelName(),
                component.specSummary(),
                offer == null ? null : offer.title(),
                offer == null ? 0L : offer.priceFen(),
                offer == null ? null : offer.priceSource(),
                offer == null ? null : offer.priceType(),
                offer != null && offer.isVerifiedPrice(),
                offer == null ? null : offer.purchaseUrl(),
                offer == null ? null : offer.platform(),
                offer == null ? null : offer.seller(),
                offer == null ? null : offer.offerId(),
                offer == null ? null : offer.matchStatus(),
                offer == null ? null : offer.verifiedAt(),
                offer == null ? null : offer.validUntil(),
                component.benchmark() == null ? null : component.benchmark().benchmarkType(),
                component.benchmark() == null ? null : component.benchmark().score());
    }
}
