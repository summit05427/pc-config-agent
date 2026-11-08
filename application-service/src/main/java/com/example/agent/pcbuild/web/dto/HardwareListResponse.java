package com.example.agent.pcbuild.web.dto;

import java.util.List;

/**
 * 候选硬件列表。
 *
 * @param catalogVersion 目录版本
 * @param total          条数
 * @param list           数据
 */
public record HardwareListResponse(String catalogVersion, int total, List<HardwareResponse> list) {
}
