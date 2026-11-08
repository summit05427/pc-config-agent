package com.example.agent.model.web.dto;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import lombok.Getter;
import lombok.Setter;
import org.springframework.format.annotation.DateTimeFormat;

/**
 * 管理端用量聚合查询参数。
 *
 * <p>聚合与列表共用 UTC 自然日口径；不提供用户、成本状态与调用结果过滤，
 * 避免「卡片总量」与「列表筛选结果」口径不一致造成误读。</p>
 */
@Getter
@Setter
public class AdminModelUsageSummaryQuery {

    @Size(max = 32, message = "provider 不能超过 32 个字符")
    private String provider;

    @Size(max = 64, message = "modelKey 不能超过 64 个字符")
    private String modelKey;

    @Pattern(regexp = "^$|MANAGED|BYOK", message = "credentialSource 只能是 MANAGED 或 BYOK")
    private String credentialSource;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate to;
}
