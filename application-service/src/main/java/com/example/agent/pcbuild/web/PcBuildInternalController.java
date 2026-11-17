package com.example.agent.pcbuild.web;

import com.example.agent.pcbuild.application.BuildResultFactory;
import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.InternalUserTokenResolver;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.pcbuild.web.dto.CompatibilityReportResponse;
import com.example.agent.pcbuild.web.dto.ComposeRequest;
import com.example.agent.pcbuild.web.dto.PartialValidateRequest;
import com.example.agent.pcbuild.web.dto.PartialValidateResponse;
import com.example.agent.pcbuild.web.dto.ValidateRequest;
import com.example.agent.pcbuild.web.dto.ValidateResponse;
import com.example.agent.shared.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * PC 配置内部接口。
 *
 * <p>指定组合与读取快照属于用户维度：除服务令牌外必须携带 {@code X-User-Token}，
 * 用户身份只从令牌 {@code sub} 解析。校验接口不落库，只需要服务令牌。</p>
 */
@RestController
@RequestMapping("/internal/v1/pc/builds")
@RequiredArgsConstructor
public class PcBuildInternalController {

    /** 用户访问令牌请求头。 */
    public static final String USER_TOKEN_HEADER = "X-User-Token";

    private final BuildSolveService buildSolveService;

    private final BuildResultFactory buildResultFactory;

    private final InternalUserTokenResolver userTokenResolver;

    /**
     * 按指定八类硬件生成方案并落快照。
     *
     * <p>价格由服务端从报价库取最低有效报价，逐件理由由服务端确定性生成，
     * 调用方只提供硬件标识与可选预算上限。</p>
     *
     * @param request   八类硬件标识与可选预算上限
     * @param userToken 用户访问令牌
     * @return 已落库方案
     */
    @PostMapping("/compose")
    public ApiResponse<BuildResultResponse> compose(
            @Valid @RequestBody ComposeRequest request,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userId = userTokenResolver.requireUserId(userToken);
        BuildResult result = buildSolveService.composeAndSnapshot(
                userId, request.toHardwareIds(), request.budgetMaxFen(), request.workloadProfile());
        return ApiResponse.success(buildResultFactory.toResponse(result));
    }

    /**
     * 校验指定配置的兼容性。
     *
     * @param request 八类硬件标识
     * @return 校验结论
     */
    @PostMapping("/validate")
    public ApiResponse<ValidateResponse> validate(@Valid @RequestBody ValidateRequest request) {
        CompatibilityReport report = buildSolveService.validate(request.toHardwareIds());
        return ApiResponse.success(new ValidateResponse(
                !report.hasFailure(),
                CompatibilityReportResponse.from(report)));
    }

    /**
     * 部分校验：只校验已选组件之间的兼容性。
     *
     * <p>不落库、不要求 {@code X-User-Token}，与 {@code /validate} 一致；
     * 与 {@code /validate} 的差别是允许任意子集，且只执行依赖组件已选全的规则。</p>
     *
     * @param request 任意子集的组件标识
     * @return 部分校验结论
     */
    @PostMapping("/validate-partial")
    public ApiResponse<PartialValidateResponse> validatePartial(
            @Valid @RequestBody PartialValidateRequest request) {
        CompatibilityReport report = buildSolveService.validatePartial(request.toHardwareIds());
        return ApiResponse.success(PartialValidateResponse.from(report));
    }

    /**
     * 读取方案快照。
     *
     * @param buildId   快照标识
     * @param userToken 用户访问令牌
     * @return 方案详情
     */
    @GetMapping("/{buildId}")
    public ApiResponse<BuildResultResponse> build(
            @PathVariable UUID buildId,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userId = userTokenResolver.requireUserId(userToken);
        return ApiResponse.success(buildSolveService.requireBuild(userId, buildId));
    }
}
