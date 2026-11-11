package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.HardwareCatalogRepository;
import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BudgetStatus;
import com.example.agent.pcbuild.domain.BuildComponent;
import com.example.agent.pcbuild.domain.BuildExplanations;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.ComponentRationale;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.web.dto.BenchmarkListResponse;
import com.example.agent.pcbuild.web.dto.BenchmarkResponse;
import com.example.agent.pcbuild.web.dto.BuildComponentResponse;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.pcbuild.web.dto.CompatibilityReportResponse;
import com.example.agent.pcbuild.web.dto.ComponentReasonResponse;
import com.example.agent.pcbuild.web.dto.OfferResponse;
import com.example.agent.pcbuild.web.dto.OfferSnapshotResponse;
import com.example.agent.pcbuild.web.dto.RequirementsResponse;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 方案结果与快照之间的装配器。
 *
 * <p>快照列按「需求 / 组件 / 报告 / 跑分 / 报价」分别存放 JSON，读取时按列还原，
 * 避免把整个响应当成一个不透明大字段而失去可查询性。</p>
 */
@Component
@RequiredArgsConstructor
public class BuildResultFactory {

    private static final TypeReference<List<BuildComponentResponse>> COMPONENT_LIST =
            new TypeReference<>() {
            };

    private final ObjectMapper objectMapper;

    private final OfferRepository offerRepository;

    private final HardwareCatalogRepository hardwareCatalogRepository;

    /**
     * @param result 领域结果
     * @return 响应
     */
    public BuildResultResponse toResponse(BuildResult result) {
        return BuildResultResponse.from(result);
    }

    /**
     * @param result 领域结果
     * @return 待写入快照
     */
    public BuildSnapshot toSnapshot(BuildResult result) {
        List<BuildComponentResponse> components = result.components().stream()
                .map(BuildComponentResponse::from)
                .toList();
        List<OfferResponse> offers = result.components().stream()
                .map(BuildComponent::offer)
                .filter(offer -> offer != null)
                .map(OfferResponse::from)
                .toList();
        List<BenchmarkResponse> benchmarks = result.components().stream()
                .map(BuildComponent::benchmark)
                .filter(benchmark -> benchmark != null)
                .map(BenchmarkResponse::from)
                .toList();
        return new BuildSnapshot(
                result.buildId(),
                result.userId(),
                null,
                write(RequirementsResponse.from(result.requirements())),
                write(components),
                result.totalPriceFen(),
                result.budgetMaxFen(),
                write(CompatibilityReportResponse.from(result.compatibilityReport())),
                write(new BenchmarkListResponse(benchmarks.size(), benchmarks)),
                write(new OfferSnapshotResponse(result.offerDataStatus(), offerRepository.priceUnit(), offers)),
                result.solverVersion(),
                result.compatibilityRuleVersion(),
                result.catalogVersion(),
                result.createdAt());
    }

    /**
     * 从快照还原响应。
     *
     * @param snapshot 快照
     * @return 响应
     */
    public BuildResultResponse fromSnapshot(BuildSnapshot snapshot) {
        RequirementsResponse requirements = read(
                snapshot.requirementsSnapshot(), RequirementsResponse.class);
        List<BuildComponentResponse> components = read(snapshot.components(), COMPONENT_LIST);
        CompatibilityReportResponse report = read(
                snapshot.compatibilityReport(), CompatibilityReportResponse.class);
        OfferSnapshotResponse offers = read(snapshot.offerSnapshot(), OfferSnapshotResponse.class);
        BudgetStatus budgetStatus = snapshot.budgetMaxFen() == null
                ? BudgetStatus.NO_BUDGET
                : BudgetStatus.WITHIN_BUDGET;
        long verifiedCount = components.stream().filter(BuildComponentResponse::verifiedPrice).count();
        long demoCount = components.stream().filter(component -> !component.verifiedPrice()).count();
        BuildRequirements domainRequirements = requirements.toRequirements();
        List<ComponentReasonResponse> componentReasons = rebuildReasons(
                snapshot, domainRequirements, components);
        return new BuildResultResponse(
                snapshot.buildId(),
                requirements,
                components,
                snapshot.totalPriceFen(),
                snapshot.budgetMaxFen(),
                budgetStatus,
                report,
                snapshot.solverVersion(),
                snapshot.compatibilityRuleVersion(),
                requirements.scoringVersion(),
                snapshot.catalogVersion(),
                offers.dataStatus(),
                verifiedCount,
                demoCount,
                snapshot.createdAt(),
                componentReasons,
                BuildExplanations.reasonSummary(domainRequirements));
    }

    /**
     * 按快照中的组件、跑分与目录规格重建理由。
     *
     * <p>方案本身（组件、价格、总价）完全来自快照；目录只用于补全规格数字。
     * 硬件已从目录移除时省略规格数字，不影响读取与方案展示。</p>
     */
    private List<ComponentReasonResponse> rebuildReasons(
            BuildSnapshot snapshot,
            BuildRequirements requirements,
            List<BuildComponentResponse> components) {

        Map<String, Benchmark> benchmarkIndex = benchmarkIndex(snapshot);
        List<BuildExplanations.ComponentInput> inputs = new ArrayList<>();
        for (BuildComponentResponse component : components) {
            Hardware hardware = hardwareCatalogRepository.findById(component.hardwareId())
                    .orElse(null);
            inputs.add(new BuildExplanations.ComponentInput(
                    component.category(),
                    component.hardwareId(),
                    hardware,
                    benchmarkIndex.get(component.hardwareId()),
                    component.priceFen()));
        }
        List<ComponentRationale> rationales = BuildExplanations.componentRationales(
                requirements, inputs, snapshot.totalPriceFen());
        return rationales.stream().map(ComponentReasonResponse::from).toList();
    }

    private Map<String, Benchmark> benchmarkIndex(BuildSnapshot snapshot) {
        BenchmarkListResponse benchmarkList = read(
                snapshot.benchmarkSnapshot(), BenchmarkListResponse.class);
        Map<String, Benchmark> index = new HashMap<>();
        if (benchmarkList == null || benchmarkList.list() == null) {
            return index;
        }
        for (BenchmarkResponse benchmark : benchmarkList.list()) {
            index.put(benchmark.hardwareId(), new Benchmark(
                    benchmark.hardwareId(),
                    benchmark.benchmarkType(),
                    benchmark.score(),
                    benchmark.secondaryScore(),
                    benchmark.rankNo(),
                    benchmark.samples(),
                    benchmark.matchMethod(),
                    benchmark.matchConfidence(),
                    benchmark.sourceName()));
        }
        return index;
    }

    private String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JacksonException ex) {
            throw new IllegalStateException("无法序列化 PC 配置快照", ex);
        }
    }

    private <T> T read(String json, Class<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JacksonException ex) {
            throw new IllegalStateException("无法反序列化 PC 配置快照", ex);
        }
    }

    private <T> T read(String json, TypeReference<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JacksonException ex) {
            throw new IllegalStateException("无法反序列化 PC 配置快照", ex);
        }
    }
}
