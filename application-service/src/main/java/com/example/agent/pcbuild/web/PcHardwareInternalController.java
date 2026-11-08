package com.example.agent.pcbuild.web;

import com.example.agent.pcbuild.application.BenchmarkQueryService;
import com.example.agent.pcbuild.application.HardwareCatalogService;
import com.example.agent.pcbuild.application.OfferQueryService;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.web.dto.BenchmarkListResponse;
import com.example.agent.pcbuild.web.dto.BenchmarkResponse;
import com.example.agent.pcbuild.web.dto.HardwareListResponse;
import com.example.agent.pcbuild.web.dto.HardwareResponse;
import com.example.agent.pcbuild.web.dto.OfferListResponse;
import com.example.agent.pcbuild.web.dto.OfferResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * PC 配置只读内部接口。
 *
 * <p>认证沿用 {@code /internal/v1/**} 的服务令牌；金额字段单位统一为人民币分，
 * 报价响应必须携带 {@code priceSource}，禁止把演示价标注为已核验。</p>
 */
@RestController
@RequestMapping("/internal/v1/pc")
@RequiredArgsConstructor
public class PcHardwareInternalController {

    private final HardwareCatalogService hardwareCatalogService;

    private final BenchmarkQueryService benchmarkQueryService;

    private final OfferQueryService offerQueryService;

    /**
     * 查询候选硬件。
     *
     * @param category 类别过滤，可选
     * @return 候选列表
     */
    @GetMapping("/hardware/candidates")
    public ApiResponse<HardwareListResponse> candidates(
            @RequestParam(required = false) String category) {
        HardwareCategory parsedCategory = parseCategory(category);
        List<Hardware> hardware = hardwareCatalogService.listCandidates(parsedCategory);
        List<HardwareResponse> list = hardware.stream().map(HardwareResponse::from).toList();
        return ApiResponse.success(new HardwareListResponse(
                hardwareCatalogService.catalogVersion(), list.size(), list));
    }

    /**
     * 查询硬件详情。
     *
     * @param hardwareId 硬件标识
     * @return 硬件详情
     */
    @GetMapping("/hardware/{hardwareId}")
    public ApiResponse<HardwareResponse> hardware(@PathVariable String hardwareId) {
        return ApiResponse.success(HardwareResponse.from(hardwareCatalogService.require(hardwareId)));
    }

    /**
     * 查询跑分。
     *
     * @param hardwareId 硬件过滤，可选
     * @param category   类别过滤，可选
     * @return 跑分列表
     */
    @GetMapping("/benchmarks")
    public ApiResponse<BenchmarkListResponse> benchmarks(
            @RequestParam(required = false) String hardwareId,
            @RequestParam(required = false) String category) {
        if (hasText(hardwareId)) {
            List<Benchmark> list = benchmarkQueryService.findByHardwareId(hardwareId)
                    .map(List::of)
                    .orElseGet(List::of);
            return ApiResponse.success(BenchmarkResponse.listOf(list));
        }
        return ApiResponse.success(
                BenchmarkResponse.listOf(benchmarkQueryService.list(parseCategory(category))));
    }

    /**
     * 查询报价。
     *
     * @param hardwareId   硬件过滤，可选
     * @param category     类别过滤，可选
     * @param verifiedOnly 是否只看人工核验价
     * @return 报价列表及来源统计
     */
    @GetMapping("/offers")
    public ApiResponse<OfferListResponse> offers(
            @RequestParam(required = false) String hardwareId,
            @RequestParam(required = false) String category,
            @RequestParam(defaultValue = "false") boolean verifiedOnly) {
        List<Offer> offers = offerQueryService.list(parseCategory(category), hardwareId, verifiedOnly);
        List<OfferResponse> list = offers.stream().map(OfferResponse::from).toList();
        return ApiResponse.success(new OfferListResponse(
                offerQueryService.dataStatus(),
                offerQueryService.priceUnit(),
                offerQueryService.verifiedCount(),
                offerQueryService.mockCount(),
                list.size(),
                list));
    }

    private HardwareCategory parseCategory(String raw) {
        if (!hasText(raw)) {
            return null;
        }
        HardwareCategory category = HardwareCategory.parse(raw);
        if (category == null) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID,
                    "未知硬件类别: " + raw);
        }
        return category;
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
