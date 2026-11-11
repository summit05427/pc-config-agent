package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.PriceSource;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 报价查询服务。
 *
 * <p>报价同时包含人工核验价与演示价。任何对外输出都必须保留 {@code price_source}，
 * 汇总统计也只按来源计数，不得把演示价并入「已核验」。</p>
 */
@Service
@RequiredArgsConstructor
public class OfferQueryService {

    private static final Comparator<Offer> STABLE_ORDER = Comparator
            .comparingInt((Offer offer) -> offer.category().ordinal())
            .thenComparing(Offer::hardwareId)
            .thenComparingLong(Offer::priceFen)
            .thenComparing(Offer::offerId);

    private final OfferRepository repository;

    /**
     * @param category     类别过滤，可为 {@code null}
     * @param hardwareId   硬件过滤，可为 {@code null}
     * @param verifiedOnly 是否只返回人工核验价
     * @return 按稳定顺序排列的报价
     */
    public List<Offer> list(HardwareCategory category, String hardwareId, boolean verifiedOnly) {
        return repository.findAll().stream()
                .filter(offer -> category == null || offer.category() == category)
                .filter(offer -> hardwareId == null || hardwareId.isBlank()
                        || hardwareId.equals(offer.hardwareId()))
                .filter(offer -> !verifiedOnly || offer.isVerifiedPrice())
                .sorted(STABLE_ORDER)
                .toList();
    }

    /**
     * 为每个硬件选出最低价的有效报价。
     *
     * <p>并列价格按 {@code offer_id} 升序，保证同一输入得到同一报价。</p>
     *
     * @param asOf             询价日期
     * @param requireVerified  是否只接受人工核验价
     * @return hardware_id → 报价
     */
    public Map<String, Offer> cheapestUsableByHardware(LocalDate asOf, boolean requireVerified) {
        Map<String, Offer> cheapest = new HashMap<>();
        for (Offer offer : list(null, null, false)) {
            if (!offer.isUsableOn(asOf)) {
                continue;
            }
            if (requireVerified && !PriceSource.OWNER_VERIFIED.equals(offer.priceSource())) {
                continue;
            }
            cheapest.merge(offer.hardwareId(), offer, (left, right) -> left.priceFen() <= right.priceFen()
                    ? left
                    : right);
        }
        return Map.copyOf(cheapest);
    }

    /**
     * @return 报价集合状态
     */
    public String dataStatus() {
        return repository.dataStatus();
    }

    /**
     * @return 价格单位
     */
    public String priceUnit() {
        return repository.priceUnit();
    }

    /**
     * @return 人工核验报价条数
     */
    public long verifiedCount() {
        return repository.findAll().stream().filter(Offer::isVerifiedPrice).count();
    }

    /**
     * @return 非人工核验报价条数，包含演示价与平台观测价
     */
    public long mockCount() {
        return repository.findAll().stream().filter(offer -> !offer.isVerifiedPrice()).count();
    }
}
