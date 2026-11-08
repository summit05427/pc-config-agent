package com.example.agent.model.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * 管理端模型连接只读查询参数。
 *
 * <p>连接状态允许 {@code ACTIVE} 与 {@code DELETED}，便于排查「为什么用户看不到连接」；
 * 空串表示不过滤。</p>
 */
@Getter
@Setter
public class AdminModelConnectionQuery extends PageQuery {

    @Size(max = 36, message = "userId 不能超过 36 个字符")
    private String userId;

    @Size(max = 32, message = "provider 不能超过 32 个字符")
    private String provider;

    @Pattern(regexp = "^$|ACTIVE|DELETED", message = "status 只能是 ACTIVE 或 DELETED")
    private String status;
}
