package com.example.agent.model.web;

import com.example.agent.model.application.CredentialLeaseService;
import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.application.ModelRuntimeService;
import com.example.agent.model.application.ModelUsageService;
import com.example.agent.model.application.UserTokenValidator;
import com.example.agent.model.domain.UsageReportResult;
import com.example.agent.model.web.dto.CredentialLeaseResponse;
import com.example.agent.model.web.dto.ModelAccessCheckRequest;
import com.example.agent.model.web.dto.ModelAvailabilityResponse;
import com.example.agent.model.web.dto.ModelTaskCreateRequest;
import com.example.agent.model.web.dto.ModelTaskResponse;
import com.example.agent.model.web.dto.UsageReportRequest;
import com.example.agent.model.web.dto.UsageReportResponse;
import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import jakarta.validation.Valid;
import java.util.UUID;
import java.util.regex.Pattern;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 模型运行时内部接口。
 *
 * <p>服务令牌证明调用方是 Agent，用户令牌证明「代表哪个用户」；两者分开传递，
 * 服务令牌不会被当成用户身份，用户身份也不接受请求体字段。</p>
 */
@RestController
@RequestMapping("/internal/v1")
@RequiredArgsConstructor
public class ModelRuntimeInternalController {

    /** 用户访问令牌请求头。 */
    public static final String USER_TOKEN_HEADER = "X-User-Token";

    /** 幂等键请求头；缺省表示调用方未启用幂等。 */
    public static final String IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";

    /**
     * 幂等键格式：长度 1..64，只允许字母、数字与 {@code . _ : -}。
     *
     * <p>键最终进入唯一索引，先在这里收窄字符集，避免上游把任意文本当键写入。</p>
     */
    private static final Pattern IDEMPOTENCY_KEY_PATTERN = Pattern.compile("[A-Za-z0-9._:-]{1,64}");

    private final ModelRuntimeService modelRuntimeService;
    private final CredentialLeaseService credentialLeaseService;
    private final ModelCatalogService modelCatalogService;
    private final ModelUsageService modelUsageService;
    private final UserTokenValidator userTokenValidator;

    /**
     * 创建运行时任务（含额度扣减）。
     *
     * <p>可选 {@code Idempotency-Key}：同键重放返回既有任务且不再扣额度，
     * 用于抵消 Agent 侧请求超时后的重试。</p>
     *
     * @param request        线程与模型选择
     * @param idempotencyKey 调用方幂等键，可缺省
     * @param userToken      用户访问令牌
     * @return 任务视图，不含凭证
     */
    @PostMapping("/model-tasks")
    public ApiResponse<ModelTaskResponse> createTask(
            @Valid @RequestBody ModelTaskCreateRequest request,
            @RequestHeader(value = IDEMPOTENCY_KEY_HEADER, required = false) String idempotencyKey,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userPublicId = userTokenValidator.requireUserId(userToken);
        String normalizedKey = normalizeIdempotencyKey(idempotencyKey);
        return ApiResponse.success(ModelTaskResponse.from(
                modelRuntimeService.createTask(
                        userPublicId, request.threadId(), request.model(), normalizedKey)));
    }

    /**
     * 归一化幂等键：空白视为未提供，格式不符直接 400。
     *
     * @param raw 原始请求头
     * @return 可用于唯一索引的键，或 {@code null}
     */
    private String normalizeIdempotencyKey(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        if (!IDEMPOTENCY_KEY_PATTERN.matcher(raw).matches()) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID);
        }
        return raw;
    }

    /**
     * 在 TTL 内读取任务。
     *
     * @param taskId    任务标识
     * @param userToken 用户访问令牌
     * @return 任务视图
     */
    @GetMapping("/model-tasks/{taskId}")
    public ApiResponse<ModelTaskResponse> readTask(
            @PathVariable UUID taskId,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userPublicId = userTokenValidator.requireUserId(userToken);
        return ApiResponse.success(ModelTaskResponse.from(
                modelRuntimeService.readTask(userPublicId, taskId)));
    }

    /**
     * 一次性兑换 BYOK 明文凭证。
     *
     * <p>只接受服务令牌：任务本身已由用户令牌创建，兑换不再重复校验用户身份；
     * 同一任务第二次兑换返回 409，密钥永远不会出现在任务创建响应里。</p>
     *
     * @param taskId 任务标识
     * @return 明文凭证与有效期
     */
    @PostMapping("/model-tasks/{taskId}/credential-lease")
    public ApiResponse<CredentialLeaseResponse> leaseCredential(@PathVariable UUID taskId) {
        return ApiResponse.success(CredentialLeaseResponse.from(credentialLeaseService.lease(taskId)));
    }

    /**
     * 校验模型是否在目录中且可用，供会话级模型保存前调用。
     *
     * @param request   模型引用
     * @param userToken 用户访问令牌
     * @return 可用性结果
     */
    @PostMapping("/model-access/check")
    public ApiResponse<ModelAvailabilityResponse> checkAccess(
            @Valid @RequestBody ModelAccessCheckRequest request,
            @RequestHeader(value = USER_TOKEN_HEADER, required = false) String userToken) {
        UUID userPublicId = userTokenValidator.requireUserId(userToken);
        return ApiResponse.success(
                ModelAvailabilityResponse.available(
                        modelCatalogService.requireAvailable(request.modelKey(), userPublicId)));
    }

    /**
     * 批量上报使用明细；归属由任务行推导，重复 invocationId 只入库一次。
     *
     * @param request 使用明细批次
     * @return 入库、重复与被拒绝条数
     */
    @PostMapping("/model-usage")
    public ApiResponse<UsageReportResponse> reportUsage(@Valid @RequestBody UsageReportRequest request) {
        UsageReportResult result = modelUsageService.report(
                request.records().stream().map(record -> record.toInput()).toList());
        return ApiResponse.success(UsageReportResponse.from(result));
    }
}
