package com.example.agent.shared.security;

import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.UUID;
import org.springframework.security.core.Authentication;

/**
 * 从已认证主体解析当前用户公开 ID。
 *
 * <p>用户身份只来自访问令牌 {@code sub}，控制器不接受路径或请求体中的用户字段，
 * 因此这里不做任何回退，解析失败即按未认证处理。</p>
 */
public final class CurrentUser {

    private CurrentUser() {
    }

    /**
     * @param authentication 当前认证信息
     * @return 令牌 {@code sub} 对应的用户公开 ID
     * @throws BusinessException 主体名称不是合法 UUID 时返回 401
     */
    public static UUID id(Authentication authentication) {
        try {
            return UUID.fromString(authentication.getName());
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(CommonErrorCode.UNAUTHORIZED);
        }
    }
}
