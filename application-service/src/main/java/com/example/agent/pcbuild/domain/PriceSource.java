package com.example.agent.pcbuild.domain;

/**
 * 报价来源常量。
 *
 * <p>{@code MOCK_DEMO} 表示演示价，绝不能在响应中表述为「已核验」；
 * 调用方必须读取 {@code price_source} 或 {@code isVerifiedPrice} 区分。</p>
 */
public final class PriceSource {

    /** 负责人人工核验的真实报价。 */
    public static final String OWNER_VERIFIED = "OWNER_VERIFIED";

    /** 电商平台检索到的观测价，未经人工核验；只能用于估算，且必须保留观测时间。 */
    public static final String PLATFORM_OBSERVED = "PLATFORM_OBSERVED";

    /** 演示用价格，未经核验。 */
    public static final String MOCK_DEMO = "MOCK_DEMO";

    private PriceSource() {
    }
}
