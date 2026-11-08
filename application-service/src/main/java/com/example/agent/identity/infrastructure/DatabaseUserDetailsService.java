package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.AuthenticatedUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

/**
 * 从数据库加载登录用户。
 *
 * <p>异常信息不包含用户名，避免把登录探测结果写进日志；
 * {@code DaoAuthenticationProvider} 默认会把「用户不存在」转换为统一的凭证错误，
 * 因此攻击者无法通过响应区分两种失败原因。</p>
 */
@Service
@RequiredArgsConstructor
public class DatabaseUserDetailsService implements UserDetailsService {

    private final UserDirectory userDirectory;

    @Override
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        return userDirectory.findByUsername(username)
                .map(AuthenticatedUser::from)
                .orElseThrow(() -> new UsernameNotFoundException("用户不存在"));
    }
}
