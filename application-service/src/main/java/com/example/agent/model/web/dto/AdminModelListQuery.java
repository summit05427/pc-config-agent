package com.example.agent.model.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * 管理端模型列表查询参数。
 *
 * <p>空串一律按「不过滤」处理；启用状态用字符串接收，避免空参数在 Boolean 绑定时报类型错误。</p>
 */
@Getter
@Setter
public class AdminModelListQuery extends PageQuery {

    @Size(max = 64, message = "keyword 不能超过 64 个字符")
    private String keyword;

    @Size(max = 32, message = "provider 不能超过 32 个字符")
    private String provider;

    @Pattern(regexp = "^$|true|false", message = "enabled 只能是 true 或 false")
    private String enabled;
}
