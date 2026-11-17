package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ModelCatalogEntry;
import com.example.agent.model.domain.ResolvedModel;
import java.util.List;

/**
 * 模型目录条目，供前端下拉展示。
 *
 * @param provider         Provider 代码
 * @param modelKey         完整模型引用
 * @param displayName      展示名
 * @param capabilities     能力标识
 * @param contextWindow    上下文窗口，未知时为空
 * @param credentialSource 凭证来源：{@code MANAGED}（平台托管）或 {@code BYOK}（我的密钥）
 */
public record ModelSummaryResponse(
        String provider,
        String modelKey,
        String displayName,
        List<String> capabilities,
        Integer contextWindow,
        String credentialSource) {

    /**
     * @param entry 目录条目
     * @return 目录响应
     */
    public static ModelSummaryResponse from(ModelCatalogEntry entry) {
        ResolvedModel model = entry.model();
        return new ModelSummaryResponse(
                model.provider(), model.reference(), model.displayName(),
                model.capabilities(), model.contextWindow(), entry.credentialSource());
    }
}
