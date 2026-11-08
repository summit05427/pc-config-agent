package com.example.agent.identity.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 管理端角色变更请求。
 *
 * <p>角色白名单固定为 {@code USER} / {@code ADMIN}：客户端不能传自定义角色，
 * 否则授权规则会出现无法预期的匹配结果。</p>
 *
 * @param roles 目标角色集合，非空且最多 10 个；重复元素由服务层去重
 */
public record AdminUserRolesUpdateRequest(
        @NotNull(message = "roles 不能为空")
        @Size(min = 1, max = 10, message = "roles 必须包含 1 到 10 个元素")
        List<
                @NotBlank(message = "角色不能为空")
                @Pattern(regexp = "USER|ADMIN", message = "角色只能是 USER 或 ADMIN")
                String> roles) {
}
