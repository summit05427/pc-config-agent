package com.example.agent.pcbuild.domain;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * 硬件规格的归一化视图。
 *
 * <p>八类硬件共用一个扁平结构，缺失字段保持 {@code null}。兼容性规则必须把
 * {@code null} 视为「无法确认」并返回 {@code UNKNOWN}，不得跳过规则，也不得猜测为通过。
 * 字段来自 Stage 1 已生成的 {@code catalog.json}，此处不做二次归一化。</p>
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonIgnoreProperties(ignoreUnknown = true)
public record HardwareSpecifications(
        // CPU
        @JsonProperty("socket") String socket,
        @JsonProperty("platform") String platform,
        @JsonProperty("core_count") Integer coreCount,
        @JsonProperty("thread_count") Integer threadCount,
        @JsonProperty("integrated_graphics") String integratedGraphics,
        @JsonProperty("includes_cooler") Boolean includesCooler,
        @JsonProperty("max_memory") String maxMemory,
        // CPU / GPU / 主板共用
        @JsonProperty("chipset") String chipset,
        // GPU
        @JsonProperty("vram_gb") Integer vramGb,
        @JsonProperty("length_mm") Integer lengthMm,
        @JsonProperty("slot_width") Integer slotWidth,
        @JsonProperty("external_power") ExternalPower externalPower,
        // CPU / GPU / 电源共用
        @JsonProperty("tdp_w") Integer tdpW,
        // 主板 / 内存
        @JsonProperty("memory_type") String memoryType,
        @JsonProperty("memory_slots") Integer memorySlots,
        @JsonProperty("max_memory_speed_mts") Integer maxMemorySpeedMts,
        @JsonProperty("m2_slot_count") Integer m2SlotCount,
        @JsonProperty("sata_ports") Integer sataPorts,
        @JsonProperty("pcie_x16_slots") Integer pcieX16Slots,
        // 主板 / 内存 / 存储 / 电源
        @JsonProperty("form_factor") String formFactor,
        // 内存 / 存储
        @JsonProperty("capacity_gb") Integer capacityGb,
        // 内存
        @JsonProperty("module_count") Integer moduleCount,
        @JsonProperty("module_size_gb") Integer moduleSizeGb,
        @JsonProperty("speed_mts") Integer speedMts,
        @JsonProperty("cas_latency") Integer casLatency,
        // 存储
        @JsonProperty("interface") String interfaceType,
        @JsonProperty("nvme") Boolean nvme,
        // 散热器
        @JsonProperty("cooler_type") String coolerType,
        @JsonProperty("height_mm") Integer heightMm,
        @JsonProperty("radiator_size_mm") Integer radiatorSizeMm,
        @JsonProperty("supported_sockets") List<String> supportedSockets,
        @JsonProperty("fanless") Boolean fanless,
        // 机箱
        @JsonProperty("supported_mainboard_form_factors") List<String> supportedMainboardFormFactors,
        @JsonProperty("max_gpu_length_mm") Integer maxGpuLengthMm,
        @JsonProperty("max_cooler_height_mm") Integer maxCoolerHeightMm,
        @JsonProperty("psu_form_factor") String psuFormFactor,
        @JsonProperty("radiator_support") String radiatorSupport,
        @JsonProperty("expansion_slots") Integer expansionSlots,
        // 电源
        @JsonProperty("wattage_w") Integer wattageW,
        @JsonProperty("efficiency") String efficiency,
        @JsonProperty("modular") String modular,
        @JsonProperty("pcie_8pin_count") Integer pcie8pinCount,
        @JsonProperty("pcie_12vhpwr_count") Integer pcie12vhpwrCount,
        @JsonProperty("sata_connectors") Integer sataConnectors) {
}
