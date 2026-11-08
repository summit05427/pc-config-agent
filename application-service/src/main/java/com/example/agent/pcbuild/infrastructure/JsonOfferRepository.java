package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * 基于 classpath {@code pc-config/offers.json} 的报价适配器。
 *
 * <p>报价按硬件聚合，并保留原始声明顺序；求解器只读取每个硬件的最低价有效报价，
 * 因此聚合顺序不影响结果。{@code price_source} 原样保留，禁止在上层改写。</p>
 */
@Repository
public class JsonOfferRepository implements OfferRepository {

    private static final String RESOURCE_PATH = "pc-config/offers.json";

    private final List<Offer> offers;

    private final Map<String, List<Offer>> byHardwareId;

    private final String dataStatus;

    private final String priceUnit;

    /**
     * @param objectMapper Spring 容器提供的 Jackson 映射器
     */
    public JsonOfferRepository(ObjectMapper objectMapper) {
        OfferFixture fixture = JsonFixtureLoader.load(objectMapper, RESOURCE_PATH, OfferFixture.class);
        this.dataStatus = fixture.dataStatus();
        this.priceUnit = fixture.priceUnit();
        Map<String, List<Offer>> index = new LinkedHashMap<>();
        for (OfferFixture.Entry entry : fixture.offers()) {
            Offer offer = toDomain(entry);
            index.computeIfAbsent(offer.hardwareId(), key -> new ArrayList<>()).add(offer);
        }
        this.byHardwareId = Map.copyOf(index);
        this.offers = List.copyOf(index.values().stream().flatMap(List::stream).toList());
    }

    @Override
    public List<Offer> findAll() {
        return offers;
    }

    @Override
    public List<Offer> findByHardwareId(String hardwareId) {
        return List.copyOf(byHardwareId.getOrDefault(hardwareId, List.of()));
    }

    @Override
    public String dataStatus() {
        return dataStatus;
    }

    @Override
    public String priceUnit() {
        return priceUnit;
    }

    private Offer toDomain(OfferFixture.Entry entry) {
        HardwareCategory category = HardwareCategory.parse(entry.category());
        if (category == null) {
            throw new BusinessException(PcBuildErrorCode.CATALOG_UNAVAILABLE,
                    "报价缺少有效类别: " + entry.offerId());
        }
        return new Offer(
                entry.offerId(),
                entry.hardwareId(),
                category,
                entry.platform(),
                entry.seller(),
                entry.shopName(),
                entry.title(),
                entry.platformSku(),
                entry.priceFen(),
                entry.priceType(),
                entry.purchaseUrl(),
                entry.verifiedAt(),
                entry.validUntil(),
                entry.matchStatus(),
                entry.priceSource(),
                entry.notes());
    }
}
