package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.application.BuildSolver;
import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.SolveFailureReason;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 求解器测试：预算边界、确定性、无解原因与硬约束不放宽。
 */
class BuildSolverTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private static final long GENEROUS_BUDGET_FEN = 2_000_000L;

    private static final long TIGHT_BUDGET_FEN = 500_000L;

    private final JsonHardwareCatalogRepository catalog =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarks =
            new JsonBenchmarkRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offers = new JsonOfferRepository(OBJECT_MAPPER);

    private final BuildSolver solver = new BuildSolver(new CompatibilityValidator());

    @Test
    void solveWithinBudget_shouldReturnCompleteDeterministicBuild() {
        BuildRequirements requirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false);

        SolveOutcome first = solve(requirements);
        SolveOutcome second = solve(requirements);

        assertThat(first.isSolved()).isTrue();
        BuildDraft build = first.build();
        assertThat(build.selection().isComplete()).isTrue();
        assertThat(build.selection().asMap()).hasSize(8);
        assertThat(build.totalPriceFen()).isPositive().isLessThanOrEqualTo(GENEROUS_BUDGET_FEN);
        assertThat(build.compatibilityReport().hasFailure()).isFalse();
        assertThat(build.offers()).hasSize(8);
        assertThat(build.offers().values()).allSatisfy(offer ->
                assertThat(offer.priceSource()).isNotBlank());
        // 相同输入必须得到完全相同的组件序列。
        assertThat(second.build().selection().idSignature())
                .isEqualTo(build.selection().idSignature());
        assertThat(second.build().totalPriceFen()).isEqualTo(build.totalPriceFen());
    }

    @Test
    void budgetShouldBeRespectedAsHardLimit() {
        SolveOutcome outcome = solve(new BuildRequirements(
                TIGHT_BUDGET_FEN, BuildScenario.BALANCED, null, null, false));

        assertThat(outcome.isSolved()).isFalse();
        assertThat(outcome.failure().reason()).isEqualTo(SolveFailureReason.BUDGET_EXCEEDED);
        assertThat(outcome.failure().minimumRequiredBudgetFen())
                .isNotNull()
                .isGreaterThan(TIGHT_BUDGET_FEN);
        // 无解时不返回任何超预算方案。
        assertThat(outcome.build()).isNull();

        long minimum = outcome.failure().minimumRequiredBudgetFen();
        SolveOutcome exact = solve(new BuildRequirements(
                minimum, BuildScenario.BALANCED, null, null, false));
        assertThat(exact.isSolved()).isTrue();
        assertThat(exact.build().totalPriceFen()).isLessThanOrEqualTo(minimum);

        SolveOutcome below = solve(new BuildRequirements(
                minimum - 1, BuildScenario.BALANCED, null, null, false));
        assertThat(below.isSolved()).isFalse();
        assertThat(below.failure().reason()).isEqualTo(SolveFailureReason.BUDGET_EXCEEDED);
        assertThat(below.failure().minimumRequiredBudgetFen()).isEqualTo(minimum);
    }

    @Test
    void withoutBudget_shouldUseValueStrategy() {
        SolveOutcome outcome = solve(new BuildRequirements(
                null, BuildScenario.CREATIVE, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().requirements().hasBudget()).isFalse();
        assertThat(outcome.build().selection().isComplete()).isTrue();
        assertThat(outcome.build().totalPriceFen()).isPositive();
    }

    @Test
    void requireVerifiedOffers_shouldReportMissingCategoriesInsteadOfUsingMockPrices() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, true));

        assertThat(outcome.isSolved()).isFalse();
        assertThat(outcome.failure().reason()).isEqualTo(SolveFailureReason.NO_CANDIDATES);
        assertThat(outcome.failure().missingCategories())
                .contains("MEMORY", "STORAGE", "COOLER", "CASE", "PSU");
        assertThat(outcome.failure().candidateCounts().get("MEMORY")).isZero();
    }

    @Test
    void minMemoryRequirement_shouldFilterCandidates() {
        SolveOutcome outcome = solve(new BuildRequirements(
                3_000_000L, BuildScenario.CREATIVE, 64, null, false));

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().selection().memory().specifications().capacityGb())
                .isEqualTo(64);
    }

    @Test
    void minStorageRequirement_shouldFilterCandidates() {
        SolveOutcome outcome = solve(new BuildRequirements(
                3_000_000L, BuildScenario.CREATIVE, null, 2048, false));

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().selection().storage().specifications().capacityGb())
                .isEqualTo(2048);
    }

    @Test
    void unknownCoolerHeight_shouldBeReportedButNotTreatedAsPass() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.OFFICE, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        CompatibilityStatus coolerHeight = outcome.build().compatibilityReport().checks().stream()
                .filter(check -> check.ruleId().equals(CompatibilityRule.COOLER_CASE_HEIGHT.ruleId()))
                .findFirst()
                .orElseThrow()
                .status();
        assertThat(coolerHeight).isEqualTo(CompatibilityStatus.UNKNOWN);
        assertThat(outcome.build().compatibilityReport().overallStatus())
                .isNotEqualTo(CompatibilityStatus.PASS);
    }

    @Test
    void selectedBuildShouldHaveOneOfferPerCategory() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.BALANCED, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        List<HardwareCategory> categories = outcome.build().offers().keySet().stream().toList();
        assertThat(categories).containsExactlyInAnyOrder(
                HardwareCategory.CPU,
                HardwareCategory.MOTHERBOARD,
                HardwareCategory.MEMORY,
                HardwareCategory.GPU,
                HardwareCategory.PSU,
                HardwareCategory.CASE,
                HardwareCategory.COOLER,
                HardwareCategory.STORAGE);
    }

    private SolveOutcome solve(BuildRequirements requirements) {
        return solver.solve(
                requirements,
                catalog.findAll(),
                offers.findAll(),
                benchmarks.findAll(),
                catalog.catalogVersion(),
                offers.dataStatus(),
                LocalDate.now());
    }
}
