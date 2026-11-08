package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.security.TokenClaims;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.stereotype.Component;

/**
 * 解析内部调用透传的用户访问令牌。
 *
 * <p>复用现有 {@link JwtDecoder}（同一签名密钥、签发方与受众），只校验
 * {@code token_use=access} 并从 {@code sub} 取用户；不新增令牌体系，
 * 也不接受请求体中的用户字段。</p>
 */
@Component
@RequiredArgsConstructor
public class InternalUserTokenResolver {

    private final JwtDecoder jwtDecoder;

    /**
     * @param rawToken {@code X-User-Token} 原文，可为 {@code null}
     * @return 用户公开 ID
     * @throws BusinessException 缺失、验签失败、用途不符或主体非法时 401 {@code 40306}
     */
    public UUID requireUserId(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            throw new BusinessException(PcBuildErrorCode.USER_TOKEN_INVALID);
        }
        try {
            Jwt jwt = jwtDecoder.decode(rawToken);
            if (!TokenClaims.TOKEN_USE_ACCESS.equals(
                    jwt.getClaimAsString(TokenClaims.TOKEN_USE_CLAIM))) {
                throw new BusinessException(PcBuildErrorCode.USER_TOKEN_INVALID);
            }
            return UUID.fromString(jwt.getSubject());
        } catch (JwtException | IllegalArgumentException ex) {
            throw new BusinessException(PcBuildErrorCode.USER_TOKEN_INVALID);
        }
    }
}
