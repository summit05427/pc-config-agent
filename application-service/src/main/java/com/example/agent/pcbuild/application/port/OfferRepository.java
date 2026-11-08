package com.example.agent.pcbuild.application.port;

import com.example.agent.pcbuild.domain.Offer;
import java.util.List;

/**
 * 报价仓储端口。
 */
public interface OfferRepository {

    /**
     * @return 全部报价
     */
    List<Offer> findAll();

    /**
     * @param hardwareId 硬件标识
     * @return 该硬件的全部报价，可能为空
     */
    List<Offer> findByHardwareId(String hardwareId);

    /**
     * @return 报价集合状态，如 {@code MIXED_DEMO}
     */
    String dataStatus();

    /**
     * @return 价格单位，固定 {@code CNY_FEN}
     */
    String priceUnit();
}
