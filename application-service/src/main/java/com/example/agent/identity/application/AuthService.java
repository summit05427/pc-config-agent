package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.AuthenticatedUser;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.infrastructure.JwtTokenService;
import com.example.agent.identity.web.dto.CurrentUserResponse;
import com.example.agent.identity.web.dto.LoginRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import com.example.agent.shared.security.IssuedToken;
import java.time.Instant;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;

/**
 * 认证服务：账号口令校验、访问令牌签发与刷新会话编排。
 *
 * <p>访问令牌有效期短，刷新令牌放在 HttpOnly Cookie 里长期有效，
 * 两者职责分离：泄露访问令牌的影响面被压缩到分钟级，刷新令牌则无法被 JS 读取。</p>
 */
@Service
@RequiredArgsConstructor
public class AuthService {

    private static final String ROLE_PREFIX = "ROLE_";

    private final AuthenticationManager authenticationManager;
    private final JwtTokenService jwtTokenService;
    private final RefreshSessionService refreshSessionService;
    private final UserDirectory userDirectory;
    private final LoginAttemptLimiter loginAttemptLimiter;
    private final AuthAuditRecorder authAuditRecorder;

    /**
     * 登录：认证通过后签发访问令牌，并开启一个新的刷新令牌族。
     *
     * <p>认证前先做失败次数检查：同一 IP + 登录名在窗口内失败过多时直接返回 429，
     * 不再触发口令校验，避免被用于暴力破解或拖慢认证线程。</p>
     *
     * @param request  登录请求
     * @param clientIp 客户端 IP，仅用于失败计数，无法解析时可为 {@code null}
     * @return 访问令牌、用户信息与需要写入 Cookie 的刷新令牌
     */
    public LoginResult login(LoginRequest request, String clientIp) {
        loginAttemptLimiter.checkAllowed(clientIp, request.username());
        Authentication authentication;
        try {
            authentication = authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(request.username(), request.password()));
        } catch (AuthenticationException ex) {
            loginAttemptLimiter.recordFailure(clientIp, request.username());
            // 认证失败会以异常结束请求，审计必须在抛出前写入（独立事务，不会随业务回滚）
            authAuditRecorder.record(AuthAuditEvent.LOGIN_FAILURE, request.username(), null);
            throw ex;
        }
        loginAttemptLimiter.clear(clientIp, request.username());
        AuthenticatedUser user = requireAuthenticatedUser(authentication);
        authAuditRecorder.record(AuthAuditEvent.LOGIN_SUCCESS, user.getUsername(), user.publicId());
        // 先开令牌族再签访问令牌：访问令牌的 sid claim 必须指向刚建立的族
        RefreshSessionService.IssuedRefreshToken refreshToken = refreshSessionService.start(user.userId());
        IssuedToken accessToken = jwtTokenService.issue(user, refreshToken.familyId());
        return new LoginResult(
                accessToken.value(),
                accessToken.expiresInSeconds(),
                new CurrentUserResponse(user.publicId(), user.getUsername(), user.roles()),
                refreshToken.rawToken(),
                refreshToken.expiresAt());
    }

    /**
     * 刷新：轮换刷新令牌并换发新的访问令牌。
     *
     * @param rawRefreshToken 来自 HttpOnly Cookie 的刷新令牌
     * @return 新访问令牌与需要写回 Cookie 的新刷新令牌
     * @throws BusinessException 刷新令牌无效、已撤销或已过期时抛 401
     */
    public RefreshResult refresh(String rawRefreshToken) {
        RefreshSessionService.RefreshedSession rotated = refreshSessionService.rotate(rawRefreshToken);
        IssuedToken accessToken =
                jwtTokenService.issue(AuthenticatedUser.from(rotated.account()), rotated.familyId());
        return new RefreshResult(
                accessToken.value(),
                accessToken.expiresInSeconds(),
                rotated.rawToken(),
                rotated.expiresAt());
    }

    /**
     * 退出登录：撤销当前刷新会话，幂等。
     *
     * @param rawRefreshToken 来自 HttpOnly Cookie 的刷新令牌，可为 {@code null}
     */
    public void logout(String rawRefreshToken) {
        refreshSessionService.revoke(rawRefreshToken);
    }

    /**
     * 退出所有设备：撤销该用户全部刷新会话。
     *
     * <p>需要访问令牌才能调用，因此不会因 Cookie 已失效而失败；撤销本身是幂等的，
     * 重复调用只是没有可撤销的行。</p>
     *
     * @param publicId 令牌 {@code sub}
     * @return 撤销的会话行数，仅用于日志
     */
    public int logoutAll(String publicId) {
        int revokedSessions = refreshSessionService.logoutAll(publicId);
        authAuditRecorder.record(AuthAuditEvent.LOGOUT_ALL, usernameOf(publicId), publicId);
        return revokedSessions;
    }

    /**
     * 从已认证的上下文提取当前用户。
     *
     * <p>令牌里只有公开 ID，登录名不写进令牌（避免改名后历史令牌仍带旧名），
     * 因此这里按公开 ID 回查一次；用户已被删除时返回 401，让前端重新登录。</p>
     *
     * @param authentication 过滤器链填充的认证信息
     */
    public CurrentUserResponse currentUser(Authentication authentication) {
        String publicId = authentication.getName();
        UserAccount account = userDirectory.findByPublicId(publicId)
                .orElseThrow(() -> new BusinessException(
                        CommonErrorCode.UNAUTHORIZED, CommonErrorCode.UNAUTHORIZED.message()));
        return new CurrentUserResponse(publicId, account.username(), extractRoles(authentication));
    }

    /** 审计需要登录名；用户已被删除时返回 {@code null}，由记录器记为 {@code unknown}。 */
    private String usernameOf(String publicId) {
        return userDirectory.findByPublicId(publicId).map(UserAccount::username).orElse(null);
    }

    private static AuthenticatedUser requireAuthenticatedUser(Authentication authentication) {
        if (authentication.getPrincipal() instanceof AuthenticatedUser user) {
            return user;
        }
        // 只有一个 DaoAuthenticationProvider，出现其他主体说明装配被改坏，属于内部错误
        throw new IllegalStateException("认证主体类型不符合预期");
    }

    private static List<String> extractRoles(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(authority -> authority.startsWith(ROLE_PREFIX))
                .map(authority -> authority.substring(ROLE_PREFIX.length()))
                .toList();
    }

    /**
     * 登录结果。
     *
     * @param accessToken      访问令牌
     * @param expiresInSeconds 访问令牌有效期秒数
     * @param user             当前用户
     * @param rawRefreshToken  刷新令牌明文，仅用于写入 Cookie
     * @param refreshExpiresAt 刷新令牌绝对过期时间
     */
    public record LoginResult(
            String accessToken,
            long expiresInSeconds,
            CurrentUserResponse user,
            String rawRefreshToken,
            Instant refreshExpiresAt) {
    }

    /**
     * 刷新结果。
     *
     * @param accessToken      新的访问令牌
     * @param expiresInSeconds 访问令牌有效期秒数
     * @param rawRefreshToken  新的刷新令牌明文，仅用于写入 Cookie
     * @param refreshExpiresAt 刷新令牌绝对过期时间
     */
    public record RefreshResult(
            String accessToken,
            long expiresInSeconds,
            String rawRefreshToken,
            Instant refreshExpiresAt) {
    }
}
