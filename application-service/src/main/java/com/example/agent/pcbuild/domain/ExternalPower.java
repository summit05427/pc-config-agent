package com.example.agent.pcbuild.domain;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 显卡外接供电需求。
 *
 * @param connectorType 接口类型，如 {@code PCIE_8PIN}、{@code PCIE_12VHPWR}
 * @param count         需要的接口数量
 */
public record ExternalPower(
        @JsonProperty("connector_type") String connectorType,
        @JsonProperty("count") Integer count) {
}
