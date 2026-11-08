package com.example.agent.pcbuild.web.dto;

import java.util.List;

/**
 * 跑分列表。
 *
 * @param total 条数
 * @param list  数据
 */
public record BenchmarkListResponse(int total, List<BenchmarkResponse> list) {
}
