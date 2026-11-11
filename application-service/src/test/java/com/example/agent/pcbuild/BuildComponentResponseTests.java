package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.domain.BuildComponent;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.web.dto.BuildComponentResponse;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 购买链接可信度：只有商品标题里能对上型号识别码时才返回链接。
 *
 * <p>平台观测价经常来自多型号混卖页面，把工控机箱挂到 NR200、把 650W/750W/850W
 * 共用一个链接都很常见；宁可不出链接，也不能把用户导到错误的商品。</p>
 */
class BuildComponentResponseTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private static final String PURCHASE_URL = "https://item.jd.com/100012043978.html";

    private static final String IMAGE_URL = "https://cdn.example.com/case.jpg";

    @Test
    void keepsLinkWhenTitleContainsModelCode() {
        BuildComponentResponse response = response(
                "Cooler Master MasterBox NR200 Mini ITX",
                "酷冷至尊 MasterBox NR200 迷你ITX机箱");

        assertThat(response.purchaseUrl()).isEqualTo(PURCHASE_URL);
        assertThat(response.imageUrl()).isEqualTo(IMAGE_URL);
    }

    @Test
    void dropsLinkWhenTitleIsAnotherProduct() {
        // 实测数据里 NR200 的报价链接指向「4 槽壁挂式工控机箱」。
        BuildComponentResponse response = response(
                "Cooler Master MasterBox NR200 Mini ITX",
                "4槽壁挂式工控机箱MATX主板机架式服务器");

        assertThat(response.purchaseUrl()).isNull();
    }

    @Test
    void dropsLinkWhenTitleOnlySharesWattage() {
        // 实测数据里 A750GL / A750GL II / A750BE 共用同一个「650W/750W/850W」混卖链接。
        BuildComponentResponse response = response(
                "MSI MAG A750GL PCIE5 II 750W Gold",
                "微星电源650W/750W/850W金牌全模组白色台式机电脑电源铜牌");

        assertThat(response.purchaseUrl()).isNull();
    }

    @Test
    void keepsLinkWhenModelHasNoDistinctiveCode() {
        // 纯数字型号（9070）区分度不足，无法据标题否定链接，保持原样。
        BuildComponentResponse response = response(
                "Radeon RX 9070 XT 16 GB",
                "蓝宝石 RX 9070 XT 16G 游戏显卡");

        assertThat(response.purchaseUrl()).isEqualTo(PURCHASE_URL);
    }

    @Test
    void keepsLinkWhenOfferHasNoUrl() {
        BuildComponentResponse response = new BuildComponentResponse(
                HardwareCategory.CASE, "case-1", "Cooler Master",
                "Cooler Master MasterBox NR200 Mini ITX", "mb=Mini ITX", null,
                "随便一个机箱", 15900L, "PLATFORM_OBSERVED", "NORMAL", false,
                null, "JD", "自营", "offer-1", "OBSERVED", null, null, null, null);

        assertThat(response.purchaseUrl()).isNull();
    }

    private BuildComponentResponse response(String modelName, String title) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(
                "{\"supported_mainboard_form_factors\":[\"Mini ITX\"],"
                        + "\"max_gpu_length_mm\":330,\"max_cooler_height_mm\":155}",
                HardwareSpecifications.class);
        Hardware hardware = new Hardware("case-1", HardwareCategory.CASE,
                "Cooler Master", modelName, null, IMAGE_URL, specifications,
                "VERIFIED", "CURRENT", "ELIGIBLE");
        Offer offer = new Offer("offer-1", "case-1", HardwareCategory.CASE,
                "JD", "自营", "酷冷至尊旗舰店", title, "100012043978", 15900L, "NORMAL",
                PURCHASE_URL, null, null, Offer.MATCH_OBSERVED, "PLATFORM_OBSERVED", null);
        return BuildComponentResponse.from(new BuildComponent(hardware, offer, null, "mb=Mini ITX"));
    }
}
