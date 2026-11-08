package com.example.agent.pcbuild.infrastructure;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDate;
import java.util.List;

/**
 * {@code offers.json} 的读取模型。
 *
 * @param dataStatus 数据状态，如 {@code MIXED_DEMO}
 * @param currency   币种
 * @param priceUnit  价格单位，{@code CNY_FEN}
 * @param offers     报价列表
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record OfferFixture(
        @JsonProperty("data_status") String dataStatus,
        @JsonProperty("currency") String currency,
        @JsonProperty("price_unit") String priceUnit,
        @JsonProperty("offers") List<Entry> offers) {

    public OfferFixture {
        offers = offers == null ? List.of() : List.copyOf(offers);
    }

    /**
     * 单条报价。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Entry(
            @JsonProperty("offer_id") String offerId,
            @JsonProperty("hardware_id") String hardwareId,
            @JsonProperty("category") String category,
            @JsonProperty("platform") String platform,
            @JsonProperty("seller") String seller,
            @JsonProperty("shop_name") String shopName,
            @JsonProperty("title") String title,
            @JsonProperty("platform_sku") String platformSku,
            @JsonProperty("price_fen") long priceFen,
            @JsonProperty("price_type") String priceType,
            @JsonProperty("purchase_url") String purchaseUrl,
            @JsonProperty("verified_at") LocalDate verifiedAt,
            @JsonProperty("valid_until") LocalDate validUntil,
            @JsonProperty("match_status") String matchStatus,
            @JsonProperty("price_source") String priceSource,
            @JsonProperty("notes") String notes) {
    }
}
