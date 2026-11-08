package com.example.agent.model.domain;

/**
 * 模型目录条目快照。
 *
 * <p>能力元数据保留原始 JSON 文本：解析失败的处理策略（抛出或降级）属于调用方的业务判断，
 * 不在读取层固化。</p>
 *
 * @param providerCode     Provider 代码
 * @param modelKey         模型键
 * @param displayName      展示名
 * @param capabilitiesJson 能力元数据 JSON
 * @param contextWindow    上下文窗口
 */
public record ModelSnapshot(
        String providerCode,
        String modelKey,
        String displayName,
        String capabilitiesJson,
        Integer contextWindow) {
}
