package com.example.agent.model.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import lombok.Getter;
import lombok.Setter;
import org.springframework.format.annotation.DateTimeFormat;

/**
 * 管理端全量使用明细查询参数。
 *
 * <p>空串一律按「不过滤」处理；时间按 UTC 自然日闭区间解释，避免管理员在不同时区下
 * 得到不同统计口径。排序只允许按发生时间升序或降序，禁止由调用方指定列名。</p>
 */
@Getter
@Setter
public class AdminModelUsageQuery extends PageQuery {

    @Size(max = 36, message = "userId 不能超过 36 个字符")
    private String userId;

    @Size(max = 32, message = "provider 不能超过 32 个字符")
    private String provider;

    @Size(max = 64, message = "modelKey 不能超过 64 个字符")
    private String modelKey;

    @Pattern(regexp = "^$|MANAGED|BYOK", message = "credentialSource 只能是 MANAGED 或 BYOK")
    private String credentialSource;

    @Pattern(
            regexp = "^$|ESTIMATED|UNKNOWN|BYOK_NOT_BILLED",
            message = "costStatus 只能是 ESTIMATED、UNKNOWN 或 BYOK_NOT_BILLED")
    private String costStatus;

    @Pattern(regexp = "^$|success|failure", message = "status 只能是 success 或 failure")
    private String status;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate to;

    @Pattern(regexp = "^$|asc|desc", message = "order 只能是 asc 或 desc")
    private String order;
}
