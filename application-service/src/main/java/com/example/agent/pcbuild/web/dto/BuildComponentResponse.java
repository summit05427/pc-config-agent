package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildComponent;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.LocalDate;
import java.util.Locale;
import java.util.regex.Pattern;

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
        String imageUrl,
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

    /** 型号识别码的最短长度；短于该值的 token（如 g5、750w）会被混卖链接误命中。 */
    private static final int MODEL_CODE_MIN_LENGTH = 4;

    private static final Pattern NON_ALPHANUMERIC = Pattern.compile("[^a-z0-9]");

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
                hardware.imageUrl(),
                offer == null ? null : offer.title(),
                offer == null ? 0L : offer.priceFen(),
                offer == null ? null : offer.priceSource(),
                offer == null ? null : offer.priceType(),
                offer != null && offer.isVerifiedPrice(),
                trustedPurchaseUrl(hardware, offer),
                offer == null ? null : offer.platform(),
                offer == null ? null : offer.seller(),
                offer == null ? null : offer.offerId(),
                offer == null ? null : offer.matchStatus(),
                offer == null ? null : offer.verifiedAt(),
                offer == null ? null : offer.validUntil(),
                component.benchmark() == null ? null : component.benchmark().benchmarkType(),
                component.benchmark() == null ? null : component.benchmark().score());
    }

    /**
     * 只返回与型号对得上的购买链接。
     *
     * <p>平台观测价常来自「多型号混卖」的商品页：一个链接同时卖 650W/750W/850W 电源，
     * 或把工控机箱的链接挂到 NR200 上。直接展示会把用户导到错误的商品，比不给链接更糟。
     * 这里用型号中最长的「字母+数字」识别码做校验；识别码缺失时无法判断，保留原链接。</p>
     */
    private static String trustedPurchaseUrl(Hardware hardware, Offer offer) {
        if (offer == null || offer.purchaseUrl() == null || offer.purchaseUrl().isBlank()) {
            return null;
        }
        String modelCode = modelCode(hardware.modelName());
        if (modelCode == null) {
            return offer.purchaseUrl();
        }
        String title = normalize(offer.title());
        return !title.isEmpty() && title.contains(modelCode) ? offer.purchaseUrl() : null;
    }

    /** 取型号中最长的字母+数字识别码，如 NR200、A750GL、9800X3D。 */
    private static String modelCode(String modelName) {
        if (modelName == null || modelName.isBlank()) {
            return null;
        }
        String longest = null;
        for (String raw : modelName.split("\\s+")) {
            String token = normalize(raw);
            boolean hasLetter = token.chars().anyMatch(Character::isLetter);
            boolean hasDigit = token.chars().anyMatch(Character::isDigit);
            if (!hasLetter || !hasDigit || token.length() < MODEL_CODE_MIN_LENGTH) {
                continue;
            }
            if (longest == null || token.length() > longest.length()) {
                longest = token;
            }
        }
        return longest;
    }

    private static String normalize(String value) {
        return value == null
                ? ""
                : NON_ALPHANUMERIC.matcher(value.toLowerCase(Locale.ROOT)).replaceAll("");
    }
}
