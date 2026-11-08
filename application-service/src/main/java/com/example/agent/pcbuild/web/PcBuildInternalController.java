package com.example.agent.pcbuild.web;

import com.example.agent.pcbuild.application.BuildResultFactory;
import com.example.agent.pcbuild.application.BuildSolveService;
import com.example.agent.pcbuild.application.InternalUserTokenResolver;
import com.example.agent.pcbuild.application.SolveExecutionResult;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.pcbuild.web.dto.CompatibilityReportResponse;
import com.example.agent.pcbuild.web.dto.SolveRequest;
import com.example.agent.pcbuild.web.dto.SolveResponse;
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
 * PC 配置求解内部接口。
 *
 * <p>求解与读取快照属于用户维度：除服务令牌外必须携带 {@code X-User-Token}，
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
     * 求解配置。
     *
     * @param request   需求
     * @param userToken 用户访问令牌
     * @return 方案或结构化失败
     */
    @PostMapping("/solve")
    public ApiResponse<SolveResponse> solve(
            @Valid @RequestBody SolveRequest request,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userId = userTokenResolver.requireUserId(userToken);
        SolveExecutionResult result = buildSolveService.solve(userId, request.toRequirements());
        if (!result.isSolved()) {
            return ApiResponse.success(SolveResponse.failed(
                    SolveResponse.Failure.from(result.failure())));
        }
        BuildResultResponse build = buildResultFactory.toResponse(result.build());
        return ApiResponse.success(SolveResponse.solved(build));
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
