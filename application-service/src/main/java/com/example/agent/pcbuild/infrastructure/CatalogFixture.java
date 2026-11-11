package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * {@code catalog.json} 的读取模型。
 *
 * <p>只负责 JSON → 领域对象的形状转换；任何字段缺失都保持 {@code null}，
 * 由领域规则决定返回 {@code UNKNOWN} 还是直接不参与求解。</p>
 *
 * @param catalogVersion 目录版本
 * @param hardware       硬件列表
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CatalogFixture(
        @JsonProperty("catalog_version") String catalogVersion,
        @JsonProperty("hardware") List<Entry> hardware) {

    public CatalogFixture {
        hardware = hardware == null ? List.of() : List.copyOf(hardware);
    }

    /**
     * 单条硬件。
     *
     * @param source 采集来源节点，图片与参考价都挂在这里
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Entry(
            @JsonProperty("hardware_id") String hardwareId,
            @JsonProperty("category") String category,
            @JsonProperty("brand") String brand,
            @JsonProperty("model_name") String modelName,
            @JsonProperty("display_name") String displayName,
            @JsonProperty("source") Source source,
            @JsonProperty("specifications") HardwareSpecifications specifications,
            @JsonProperty("data_quality_status") String dataQualityStatus,
            @JsonProperty("lifecycle_status") String lifecycleStatus,
            @JsonProperty("recommendation_status") String recommendationStatus) {
    }

    /**
     * 采集来源节点。
     *
     * <p>只有部分条目带图片，缺失是正常状态，不能编造占位图。</p>
     *
     * @param imageUrl 商品图地址，可能为空
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Source(@JsonProperty("image_url") String imageUrl) {
    }
}
