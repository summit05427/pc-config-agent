package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.security.TokenClaims;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.stereotype.Component;

/**
 * 校验内部调用中透传的用户访问令牌。
 *
 * <p>服务令牌只证明「Agent 是可信调用方」，不能证明「代表哪个用户」。因此
 * {@code model-tasks} 与 {@code model-access/check} 额外要求 {@code X-User-Token}，
 * 用户身份从令牌 {@code sub} 解析，绝不接受请求体里的用户字段。</p>
 */
@Component
@RequiredArgsConstructor
public class UserTokenValidator {

    private final JwtDecoder jwtDecoder;

    /**
     * @param rawToken 用户访问令牌原文，可为 {@code null}
     * @return 令牌主体对应的 {@code users.public_id}
     * @throws BusinessException 缺失、验签失败、用途不是 access 或主体不是 UUID 时抛出 401
     */
    public UUID requireUserId(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            throw new BusinessException(ModelErrorCode.USER_TOKEN_INVALID);
        }
        try {
            Jwt jwt = jwtDecoder.decode(rawToken);
            if (!TokenClaims.TOKEN_USE_ACCESS.equals(
                    jwt.getClaimAsString(TokenClaims.TOKEN_USE_CLAIM))) {
                throw new BusinessException(ModelErrorCode.USER_TOKEN_INVALID);
            }
            return UUID.fromString(jwt.getSubject());
        } catch (JwtException | IllegalArgumentException ex) {
            throw new BusinessException(ModelErrorCode.USER_TOKEN_INVALID);
        }
    }
}
