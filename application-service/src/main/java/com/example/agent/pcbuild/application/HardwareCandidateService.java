package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.ExternalPower;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.Offer;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 候选硬件决策查询服务。
 *
 * <p>候选接口一次返回多类硬件，报价必须「一次取全量 + 建索引」后再映射，
 * 不能在候选循环里逐条查库；取价口径与求解器完全一致（{@link BuildSolver#cheapestUsableOffers}
 * 且 {@code requireVerified=false}），因此求解用的价格与候选展示的价格不会漂移。</p>
 *
 * <p>{@code missingFields} 只统计兼容性规则真正读取的规格字段：命名沿用
 * {@code catalog.json} 的 snake_case 规格键（与 {@code unverified_fields} 同一写法），
 * 它是 {@code data_quality_status=PARTIAL} 的具体化——这些字段缺失会让相关规则返回
 * {@code UNKNOWN}，但不会阻止硬件进入候选。</p>
 */
@Service
@RequiredArgsConstructor
public class HardwareCandidateService {

    private final HardwareCatalogService hardwareCatalogService;

    private final BuildSolver solver;

    private final OfferRepository offerRepository;

    /**
     * 查询候选硬件，附带最低可用报价与兼容性关键字段缺失项。
     *
     * @param category 类别过滤，可为 {@code null}
     * @return 按目录稳定顺序排列的候选
     */
    public List<HardwareCandidate> listCandidates(HardwareCategory category) {
        Map<String, Offer> cheapestOffers = solver.cheapestUsableOffers(
                offerRepository.findAll(), LocalDate.now(), false);
        return hardwareCatalogService.listCandidates(category).stream()
                .map(hardware -> new HardwareCandidate(
                        hardware,
                        priceOf(cheapestOffers, hardware),
                        missingCompatibilityFields(hardware)))
                .toList();
    }

    /**
     * @return 目录版本
     */
    public String catalogVersion() {
        return hardwareCatalogService.catalogVersion();
    }

    /**
     * 最低可用报价；没有可用报价时返回 {@code null}。
     *
     * <p>目录里的 {@code price_cny} 只是录入参考价，币种与时效都未经核验，
     * 不能作为报价兜底。</p>
     */
    private Long priceOf(Map<String, Offer> cheapestOffers, Hardware hardware) {
        Offer offer = cheapestOffers.get(hardware.hardwareId());
        return offer == null ? null : offer.priceFen();
    }

    /**
     * 列出该硬件在兼容性规则所读字段上的缺失项。
     *
     * <p>字段清单与 {@link CompatibilityValidator} 的判定字段一一对应；规则本身仍是唯一
     * 判定方，这里只做「是否有值」的静态汇总。</p>
     */
    private List<String> missingCompatibilityFields(Hardware hardware) {
        HardwareSpecifications spec = hardware.specifications();
        List<String> missing = new ArrayList<>();
        switch (hardware.category()) {
            case CPU -> {
                addIfBlank(missing, "socket", spec.socket());
                addIfNull(missing, "tdp_w", spec.tdpW());
            }
            case MOTHERBOARD -> {
                addIfBlank(missing, "socket", spec.socket());
                addIfBlank(missing, "memory_type", spec.memoryType());
                addIfBlank(missing, "form_factor", spec.formFactor());
                addIfNull(missing, "memory_slots", spec.memorySlots());
                addIfNull(missing, "m2_slot_count", spec.m2SlotCount());
                addIfNull(missing, "sata_ports", spec.sataPorts());
            }
            case MEMORY -> {
                addIfBlank(missing, "memory_type", spec.memoryType());
                addIfNull(missing, "module_count", spec.moduleCount());
            }
            case GPU -> {
                addIfNull(missing, "length_mm", spec.lengthMm());
                addIfNull(missing, "tdp_w", spec.tdpW());
                addIfExternalPowerMissing(missing, spec.externalPower());
            }
            case PSU -> {
                addIfNull(missing, "wattage_w", spec.wattageW());
                addIfNull(missing, "pcie_8pin_count", spec.pcie8pinCount());
                addIfNull(missing, "pcie_12vhpwr_count", spec.pcie12vhpwrCount());
            }
            case CASE -> {
                addIfEmpty(missing, "supported_mainboard_form_factors",
                        spec.supportedMainboardFormFactors());
                addIfNull(missing, "max_gpu_length_mm", spec.maxGpuLengthMm());
                addIfNull(missing, "max_cooler_height_mm", spec.maxCoolerHeightMm());
            }
            case COOLER -> {
                addIfEmpty(missing, "supported_sockets", spec.supportedSockets());
                addIfNull(missing, "height_mm", spec.heightMm());
            }
            case STORAGE -> addIfBlank(missing, "interface", spec.interfaceType());
        }
        return List.copyOf(missing);
    }

    /** 外接供电是复合字段：接口类型或数量任一缺失都算缺失。 */
    private void addIfExternalPowerMissing(List<String> missing, ExternalPower externalPower) {
        boolean isMissing = externalPower == null
                || isBlank(externalPower.connectorType())
                || externalPower.count() == null
                || externalPower.count() <= 0;
        if (isMissing) {
            missing.add("external_power");
        }
    }

    private void addIfBlank(List<String> missing, String fieldName, String value) {
        if (isBlank(value)) {
            missing.add(fieldName);
        }
    }

    private void addIfNull(List<String> missing, String fieldName, Integer value) {
        if (value == null) {
            missing.add(fieldName);
        }
    }

    private void addIfEmpty(List<String> missing, String fieldName, List<String> values) {
        if (values == null || values.isEmpty()) {
            missing.add(fieldName);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
