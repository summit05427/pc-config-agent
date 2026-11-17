package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScoring;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.Offer;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 配置草稿组装与取价工具。
 *
 * <p>选型决策已下沉到 Agent，Java 只保留事实能力：按硬件聚合最低有效报价，
 * 把调用方指定的八类硬件组装成带兼容性报告与评分的草稿。这里不搜索、不比较、不挑选方案。</p>
 */
@Component
@RequiredArgsConstructor
public class BuildSolver {

    private final CompatibilityValidator compatibilityValidator;

    /**
     * 按硬件聚合最低有效报价。
     *
     * <p>「指定组合生成方案」与候选展示必须使用同一取价口径，因此集中在这一处实现。</p>
     *
     * @param offers          全部报价
     * @param pricingDate     询价日期，用于判断有效期
     * @param requireVerified 是否只接受人工核验报价
     * @return 按硬件标识索引的最低有效报价
     */
    public Map<String, Offer> cheapestUsableOffers(
            List<Offer> offers, LocalDate pricingDate, boolean requireVerified) {
        Map<String, Offer> cheapest = new HashMap<>();
        for (Offer offer : offers) {
            if (!offer.isUsableOn(pricingDate)) {
                continue;
            }
            if (requireVerified && !offer.isVerifiedPrice()) {
                continue;
            }
            cheapest.merge(offer.hardwareId(), offer, (left, right) -> {
                if (left.priceFen() != right.priceFen()) {
                    return left.priceFen() <= right.priceFen() ? left : right;
                }
                return left.offerId().compareTo(right.offerId()) <= 0 ? left : right;
            });
        }
        return Map.copyOf(cheapest);
    }

    /**
     * 由已选组合组装方案草稿。
     *
     * <p>报价、总价与评分只在这里计算，避免出现第二套价格口径。</p>
     *
     * @param requirements     需求，决定评分与逐件理由的文案口径
     * @param selection        已选八类硬件，必须完整
     * @param offersByHardware 按硬件标识索引的最低有效报价
     * @param benchmarkIndex   按硬件标识索引的跑分
     * @param catalogVersion   目录版本
     * @param offerDataStatus  报价数据状态
     * @return 方案草稿
     * @throws NullPointerException 任一类别缺少报价时
     */
    public BuildDraft toDraft(
            BuildRequirements requirements,
            HardwareSelection selection,
            Map<String, Offer> offersByHardware,
            Map<String, Benchmark> benchmarkIndex,
            String catalogVersion,
            String offerDataStatus) {

        Map<HardwareCategory, Offer> offers = new LinkedHashMap<>();
        Map<HardwareCategory, Benchmark> benchmarks = new LinkedHashMap<>();
        long totalPrice = 0L;
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            Hardware hardware = selection.get(category);
            Offer offer = Objects.requireNonNull(offersByHardware.get(hardware.hardwareId()),
                    () -> "缺少报价: " + hardware.hardwareId());
            totalPrice += offer.priceFen();
            offers.put(category, offer);
            Benchmark benchmark = benchmarkIndex.get(hardware.hardwareId());
            if (benchmark != null) {
                benchmarks.put(category, benchmark);
            }
        }
        CompatibilityReport report = compatibilityValidator.validate(selection);
        return new BuildDraft(
                requirements,
                selection,
                offers,
                benchmarks,
                totalPrice,
                report,
                BuildScoring.totalScore(requirements, selection.asMap(), benchmarkIndex),
                catalogVersion,
                offerDataStatus);
    }
}
