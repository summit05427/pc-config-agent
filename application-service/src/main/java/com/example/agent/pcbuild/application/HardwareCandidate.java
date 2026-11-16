package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.Hardware;
import java.util.List;

/**
 * 候选硬件 + 决策所需的两项附加信息。
 *
 * <p>只服务候选查询接口：{@code priceFen} 与 {@code missingFields} 让 Agent 不必再逐个
 * 硬件查询报价与规格缺失，避免 N+1 调用。</p>
 *
 * @param hardware      硬件主数据
 * @param priceFen      该硬件的最低可用报价，单位分；没有可用报价时为 {@code null}，
 *                      绝不用目录里的参考价兜底
 * @param missingFields 兼容性关键字段的缺失项，字段名与 {@code catalog.json} 的
 *                      {@code specifications} 键一致；为空表示关键字段齐全
 */
public record HardwareCandidate(Hardware hardware, Long priceFen, List<String> missingFields) {

    public HardwareCandidate {
        missingFields = missingFields == null ? List.of() : List.copyOf(missingFields);
    }
}
