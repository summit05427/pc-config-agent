package com.example.agent.model.web.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;
import java.time.Instant;

/**
 * 新增定价版本的请求体。
 *
 * <p>单价按「每百万 token」计，与 {@code model_pricing} 表定义一致；
 * 生效时间由运营显式指定，历史成本不会因后续调价被重算。</p>
 *
 * @param currency              币种，空值按 USD 处理
 * @param inputPricePerMillion  每百万输入 token 单价
 * @param outputPricePerMillion 每百万输出 token 单价
 * @param effectiveFrom         生效时间（UTC）
 */
public record AdminModelPricingCreateRequest(
        @Pattern(regexp = "^[A-Za-z]{3}$", message = "currency 必须是 3 位字母币种")
        String currency,

        @NotNull(message = "inputPricePerMillion 不能为空")
        @DecimalMin(value = "0", message = "inputPricePerMillion 不能为负数")
        @Digits(integer = 12, fraction = 6, message = "inputPricePerMillion 最多 12 位整数与 6 位小数")
        BigDecimal inputPricePerMillion,

        @NotNull(message = "outputPricePerMillion 不能为空")
        @DecimalMin(value = "0", message = "outputPricePerMillion 不能为负数")
        @Digits(integer = 12, fraction = 6, message = "outputPricePerMillion 最多 12 位整数与 6 位小数")
        BigDecimal outputPricePerMillion,

        @NotNull(message = "effectiveFrom 不能为空")
        Instant effectiveFrom) {
}
