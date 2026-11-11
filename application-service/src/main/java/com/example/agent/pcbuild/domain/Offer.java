package com.example.agent.pcbuild.domain;

import java.time.LocalDate;
import java.util.Objects;

/**
 * 市场报价。
 *
 * <p>金额单位是人民币分（{@code price_fen}），全程使用 {@code long}，禁止浮点。
 * 只有 {@code match_status} 属于已匹配状态、价格为正、且未过期的报价才能参与求解。</p>
 *
 * @param offerId    报价标识
 * @param hardwareId 对应硬件标识
 * @param category   所属类别
 * @param platform   平台
 * @param seller     商家
 * @param shopName   店铺名
 * @param title      商品标题
 * @param platformSku 平台商品 ID
 * @param priceFen   价格，单位分
 * @param priceType  价格类型，如 {@code NORMAL}
 * @param purchaseUrl 核验链接
 * @param verifiedAt 核验日期，可为 {@code null}（演示价）
 * @param validUntil 有效期，可为 {@code null}
 * @param matchStatus 匹配状态
 * @param priceSource 价格来源，{@code OWNER_VERIFIED}、{@code PLATFORM_OBSERVED} 或 {@code MOCK_DEMO}
 * @param notes      备注
 */
public record Offer(
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
        String notes) {

    /** 人工核验且可进入推荐的匹配状态。 */
    public static final String MATCH_VERIFIED = "VERIFIED";

    /** 演示价使用的匹配状态；可参与演示求解，但必须标注来源。 */
    public static final String MATCH_MOCK = "MOCK";

    /** 平台观测价：来自电商检索结果，未经人工核验，可用于估算但不得表述为已核验。 */
    public static final String MATCH_OBSERVED = "OBSERVED";

    /**
     * @return 是否为人工核验价
     */
    public boolean isVerifiedPrice() {
        return PriceSource.OWNER_VERIFIED.equals(priceSource);
    }

    /**
     * 判断报价在给定日期是否可用于求解。
     *
     * <p>有效条件：价格为正、匹配状态为 {@code VERIFIED}、{@code MOCK} 或 {@code OBSERVED}、
     * 且没有过期（{@code valid_until} 为空视为长期有效）。是否接受观测价由调用方的
     * {@code requireVerified} 决定，不能靠本方法兜底。</p>
     *
     * @param asOf 询价日期
     * @return 可用于求解时为 {@code true}
     */
    public boolean isUsableOn(LocalDate asOf) {
        boolean isMatched = MATCH_VERIFIED.equalsIgnoreCase(matchStatus)
                || MATCH_MOCK.equalsIgnoreCase(matchStatus)
                || MATCH_OBSERVED.equalsIgnoreCase(matchStatus);
        boolean isNotExpired = validUntil == null
                || (asOf != null && !validUntil.isBefore(asOf));
        return isMatched && priceFen > 0 && isNotExpired && Objects.nonNull(hardwareId);
    }
}
