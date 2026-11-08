package com.example.agent.identity.domain;

import java.util.Collection;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

/**
 * 认证通过后的登录主体。
 *
 * <p>Spring Security 的 {@link UserDetails} 只有用户名，无法携带对外公开 ID；
 * 这里额外保存 {@code publicId}，让 JWT 签发直接使用它而不必回查数据库。</p>
 */
public final class AuthenticatedUser implements UserDetails {

    private static final String ROLE_PREFIX = "ROLE_";

    private final Long userId;
    private final String publicId;
    private final String username;
    private final String passwordHash;
    private final List<String> roles;
    private final boolean isEnabled;

    private AuthenticatedUser(
            Long userId,
            String publicId,
            String username,
            String passwordHash,
            List<String> roles,
            boolean isEnabled) {
        this.userId = userId;
        this.publicId = publicId;
        this.username = username;
        this.passwordHash = passwordHash;
        this.roles = List.copyOf(roles);
        this.isEnabled = isEnabled;
    }

    /**
     * 由领域对象构造登录主体。
     *
     * @param account 用户账号
     * @return 带公开 ID 的登录主体
     */
    public static AuthenticatedUser from(UserAccount account) {
        return new AuthenticatedUser(
                account.id(),
                account.publicId(),
                account.username(),
                account.passwordHash(),
                account.roles(),
                account.status().isActive());
    }

    /**
     * 内部主键，仅供服务端建立刷新会话等内部关联使用。
     *
     * @return 用户内部自增主键
     */
    public Long userId() {
        return userId;
    }

    public String publicId() {
        return publicId;
    }

    public List<String> roles() {
        return roles;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return roles.stream()
                .map(role -> new SimpleGrantedAuthority(ROLE_PREFIX + role))
                .toList();
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return isEnabled;
    }
}
