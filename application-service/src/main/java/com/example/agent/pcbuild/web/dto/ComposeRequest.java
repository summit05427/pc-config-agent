package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.pcbuild.domain.WorkloadProfile;
import com.example.agent.shared.error.BusinessException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

/**
 * 指定八类硬件生成方案的请求。
 *
 * <p>组件字段与校验规则和 {@link ValidateRequest} 完全一致，直接复用同一份 DTO，
 * 避免两份「八类标识 → 类别映射」的解析逻辑逐渐漂移。</p>
 *
 * @param components   八类硬件标识
 * @param budgetMaxFen 预算上限，单位人民币分；可为 {@code null}，非空时必须为正，
 *                     由服务端在写快照前强制校验
 * @param workloadProfile 工作负载画像；为空表示调用方未声明，回落到 GENERAL
 */
public record ComposeRequest(
        @NotNull @Valid ValidateRequest components,
        @Min(value = 1, message = "预算上限至少为 1 分") Long budgetMaxFen,
        WorkloadProfile workloadProfile) {

    /**
     * 转换为类别到硬件标识的映射。
     *
     * @return 八类硬件标识
     * @throws BusinessException 组件或任一类别缺失时 400 {@code 40303}
     */
    public Map<HardwareCategory, String> toHardwareIds() {
        if (components == null) {
            throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE, "缺少硬件组件");
        }
        return components.toHardwareIds();
    }
}
