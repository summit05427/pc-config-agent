package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * PostgreSQL 用户仓储实现。
 *
 * <p>{@code roles} 在库中以逗号分隔文本保存，读写边界在这一层完成转换，
 * 领域层只看到 {@code List<String>}。</p>
 */
@Component
@RequiredArgsConstructor
public class MyBatisUserDirectory implements UserDirectory {

    private static final String ROLE_SEPARATOR = ",";
    private static final String LIKE_WILDCARD = "%";

    private final UserMapper userMapper;

    @Override
    public Optional<UserAccount> findByUsername(String username) {
        return Optional.ofNullable(userMapper.findByUsername(username)).map(MyBatisUserDirectory::toAccount);
    }

    @Override
    public Optional<UserAccount> findByPublicId(String publicId) {
        return Optional.ofNullable(userMapper.findByPublicId(publicId)).map(MyBatisUserDirectory::toAccount);
    }

    @Override
    public Optional<UserAccount> findById(Long id) {
        return Optional.ofNullable(userMapper.findById(id)).map(MyBatisUserDirectory::toAccount);
    }

    @Override
    public UserAccount create(String username, String passwordHash, List<String> roles) {
        UserRow row = new UserRow();
        row.setPublicId(UUID.randomUUID().toString());
        row.setUsername(username);
        row.setPasswordHash(passwordHash);
        row.setRoles(String.join(ROLE_SEPARATOR, roles));
        row.setStatus(UserStatus.ACTIVE.name());
        userMapper.insert(row);
        return toAccount(row);
    }

    @Override
    public Optional<UserProfile> findProfileByPublicId(String publicId) {
        return Optional.ofNullable(userMapper.findByPublicId(publicId)).map(MyBatisUserDirectory::toProfile);
    }

    @Override
    public void updateProfile(String publicId, String displayName, String email, String bio) {
        userMapper.updateProfile(publicId, displayName, email, bio);
    }

    @Override
    public void updatePasswordHash(String publicId, String passwordHash) {
        userMapper.updatePasswordHash(publicId, passwordHash);
    }

    @Override
    public long countUsers(String keyword, UserStatus status) {
        return userMapper.countUsers(toLikePattern(keyword), statusName(status));
    }

    @Override
    public List<UserProfile> listUsers(String keyword, UserStatus status, long offset, int size) {
        return userMapper.listUsers(toLikePattern(keyword), statusName(status), offset, size).stream()
                .map(MyBatisUserDirectory::toProfile)
                .toList();
    }

    /**
     * 拼 {@code LIKE} 通配符是持久化细节；application 只传去空白的原始匹配串。
     */
    private static String toLikePattern(String keyword) {
        return keyword == null ? null : LIKE_WILDCARD + keyword + LIKE_WILDCARD;
    }

    @Override
    public int updateStatus(String publicId, UserStatus status) {
        return userMapper.updateStatus(publicId, status.name());
    }

    @Override
    public int updateRoles(String publicId, List<String> roles) {
        return userMapper.updateRoles(publicId, String.join(ROLE_SEPARATOR, roles));
    }

    @Override
    public long countActiveAdmins() {
        return userMapper.countActiveAdmins();
    }

    /** 状态过滤为空时不传给 SQL，避免把 {@code null} 当成一个真实取值。 */
    private static String statusName(UserStatus status) {
        return status == null ? null : status.name();
    }

    private static UserAccount toAccount(UserRow row) {
        return new UserAccount(
                row.getId(),
                row.getPublicId(),
                row.getUsername(),
                row.getPasswordHash(),
                splitRoles(row.getRoles()),
                UserStatus.from(row.getStatus()));
    }

    private static UserProfile toProfile(UserRow row) {
        return new UserProfile(
                row.getPublicId(),
                row.getUsername(),
                row.getDisplayName(),
                row.getEmail(),
                row.getBio(),
                splitRoles(row.getRoles()),
                UserStatus.from(row.getStatus()),
                row.getCreatedAt(),
                row.getUpdatedAt());
    }

    private static List<String> splitRoles(String roles) {
        if (roles == null || roles.isBlank()) {
            return List.of();
        }
        return Arrays.stream(roles.split(ROLE_SEPARATOR))
                .map(String::trim)
                .filter(role -> !role.isEmpty())
                .toList();
    }
}
