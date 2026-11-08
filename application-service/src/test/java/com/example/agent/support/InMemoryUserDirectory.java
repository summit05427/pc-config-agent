package com.example.agent.support;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.UnaryOperator;

/**
 * 测试用内存用户仓储。
 *
 * <p>认证集成测试要验证完整的过滤器链，不应该依赖真实数据库；
 * 生产实现由 {@code MyBatisUserDirectory} 提供，两者行为在接口上等价。
 * 这里额外保存 {@code displayName} / {@code email} / {@code bio} 与时间戳，
 * 以支持资料读写接口的端到端断言。</p>
 */
public class InMemoryUserDirectory implements UserDirectory {

    private static final String ADMIN_ROLE = "ADMIN";

    private final Map<String, UserAccount> usersByUsername = new ConcurrentHashMap<>();
    private final Map<String, ProfileFields> profilesByPublicId = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public Optional<UserAccount> findByUsername(String username) {
        return Optional.ofNullable(usersByUsername.get(username));
    }

    @Override
    public Optional<UserAccount> findByPublicId(String publicId) {
        return usersByUsername.values().stream()
                .filter(account -> account.publicId().equals(publicId))
                .findFirst();
    }

    @Override
    public Optional<UserAccount> findById(Long id) {
        return usersByUsername.values().stream()
                .filter(account -> account.id().equals(id))
                .findFirst();
    }

    @Override
    public UserAccount create(String username, String passwordHash, List<String> roles) {
        UserAccount account = new UserAccount(
                sequence.incrementAndGet(),
                UUID.randomUUID().toString(),
                username,
                passwordHash,
                List.copyOf(roles),
                UserStatus.ACTIVE);
        usersByUsername.put(username, account);
        Instant now = Instant.now();
        profilesByPublicId.put(account.publicId(), new ProfileFields(null, null, null, now, now));
        return account;
    }

    @Override
    public Optional<UserProfile> findProfileByPublicId(String publicId) {
        return findByPublicId(publicId).map(this::toProfile);
    }

    @Override
    public void updateProfile(String publicId, String displayName, String email, String bio) {
        ProfileFields fields = profilesByPublicId.get(publicId);
        if (fields == null) {
            return;
        }
        profilesByPublicId.put(publicId, new ProfileFields(displayName, email, bio, fields.createdAt(), Instant.now()));
    }

    @Override
    public void updatePasswordHash(String publicId, String passwordHash) {
        replaceUser(publicId, account -> new UserAccount(
                account.id(), account.publicId(), account.username(), passwordHash,
                account.roles(), account.status()));
    }

    @Override
    public long countUsers(String keyword, UserStatus status) {
        return matchingProfiles(keyword, status).size();
    }

    @Override
    public List<UserProfile> listUsers(String keyword, UserStatus status, long offset, int size) {
        return matchingProfiles(keyword, status).stream()
                .skip(offset)
                .limit(size)
                .toList();
    }

    @Override
    public int updateStatus(String publicId, UserStatus status) {
        return replaceUser(publicId, account -> new UserAccount(
                account.id(), account.publicId(), account.username(), account.passwordHash(),
                account.roles(), status)) ? 1 : 0;
    }

    @Override
    public int updateRoles(String publicId, List<String> roles) {
        return replaceUser(publicId, account -> new UserAccount(
                account.id(), account.publicId(), account.username(), account.passwordHash(),
                List.copyOf(roles), account.status())) ? 1 : 0;
    }

    @Override
    public long countActiveAdmins() {
        return usersByUsername.values().stream()
                .filter(account -> account.status().isActive())
                .filter(account -> account.roles().contains(ADMIN_ROLE))
                .count();
    }

    /**
     * 模拟 SQL 的过滤与排序：生产查询按 {@code created_at DESC, id DESC} 排，
     * 内存实现保持同样顺序，避免测试结果依赖用户插入顺序。
     */
    private List<UserProfile> matchingProfiles(String keyword, UserStatus status) {
        return usersByUsername.values().stream()
                .filter(account -> status == null || account.status() == status)
                .filter(account -> matchesKeyword(account, keyword))
                .sorted(Comparator.comparing(this::createdAt)
                        .thenComparing(UserAccount::id)
                        .reversed())
                .map(this::toProfile)
                .toList();
    }

    /**
     * 端口传入的是已去空白的原始匹配串，这里按 SQL {@code ILIKE '%keyword%'} 的语义做
     * 等价的忽略大小写子串匹配；邮箱为空时只匹配登录名。
     */
    private boolean matchesKeyword(UserAccount account, String keyword) {
        if (keyword == null) {
            return true;
        }
        String needle = keyword.toLowerCase(Locale.ROOT);
        ProfileFields fields = profilesByPublicId.get(account.publicId());
        String email = fields == null ? null : fields.email();
        return account.username().toLowerCase(Locale.ROOT).contains(needle)
                || (email != null && email.toLowerCase(Locale.ROOT).contains(needle));
    }

    /** UserAccount 不可变：命中后整体替换账号，并刷新资料更新时间。 */
    private boolean replaceUser(String publicId, UnaryOperator<UserAccount> replacement) {
        UserAccount existing = findByPublicId(publicId).orElse(null);
        if (existing == null) {
            return false;
        }
        usersByUsername.put(existing.username(), replacement.apply(existing));
        ProfileFields fields = profilesByPublicId.get(publicId);
        if (fields != null) {
            profilesByPublicId.put(publicId, new ProfileFields(
                    fields.displayName(), fields.email(), fields.bio(), fields.createdAt(), Instant.now()));
        }
        return true;
    }

    private Instant createdAt(UserAccount account) {
        ProfileFields fields = profilesByPublicId.get(account.publicId());
        return fields == null ? Instant.EPOCH : fields.createdAt();
    }

    private UserProfile toProfile(UserAccount account) {
        ProfileFields fields = profilesByPublicId.get(account.publicId());
        return new UserProfile(
                account.publicId(),
                account.username(),
                fields.displayName(),
                fields.email(),
                fields.bio(),
                account.roles(),
                account.status(),
                fields.createdAt(),
                fields.updatedAt());
    }

    /**
     * 内存里的资料字段。全部可空，与数据库列语义保持一致。
     */
    private record ProfileFields(
            String displayName,
            String email,
            String bio,
            Instant createdAt,
            Instant updatedAt) {
    }
}
