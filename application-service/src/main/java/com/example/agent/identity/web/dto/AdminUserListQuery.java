package com.example.agent.identity.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * 管理端用户列表的查询参数。
 *
 * <p>继承 {@link PageQuery} 复用默认页大小与上限校验；空串按「不过滤」处理，
 * 因此状态与关键字都允许空值。</p>
 */
@Getter
@Setter
public class AdminUserListQuery extends PageQuery {

    @Size(max = 64, message = "keyword 不能超过 64 个字符")
    private String keyword;

    @Pattern(regexp = "^$|ACTIVE|DISABLED", message = "status 只能是 ACTIVE 或 DISABLED")
    private String status;
}
