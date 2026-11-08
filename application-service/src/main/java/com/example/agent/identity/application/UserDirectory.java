package com.example.agent.identity.application;

import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.domain.UserStatus;
import java.util.List;
import java.util.Optional;

/**
 * 用户数据访问端口。
 *
 * <p>用端口隔离存储实现：生产走 MyBatis + PostgreSQL，测试用内存实现替换，
 * 让认证集成测试不需要数据库也能跑完整过滤器链。</p>
 */
public interface UserDirectory {

    /**
     * 按登录名查询用户。
     *
     * @param username 登录名
     * @return 命中的用户；不存在时返回空
     */
    Optional<UserAccount> findByUsername(String username);

    /**
     * 按对外公开 ID 查询用户。
     *
     * @param publicId 公开 ID（UUID 字符串）
     * @return 命中的用户；不存在时返回空
     */
    Optional<UserAccount> findByPublicId(String publicId);

    /**
     * 按内部主键查询用户。
     *
     * <p>只供服务端内部使用（如刷新令牌时回查用户），内部主键绝不对外暴露。</p>
     *
     * @param id 内部主键
     * @return 命中的用户；不存在时返回空
     */
    Optional<UserAccount> findById(Long id);

    /**
     * 创建用户，公开 ID 由服务端生成。
     *
     * @param username     登录名，必须唯一
     * @param passwordHash 口令摘要
     * @param roles        业务角色，不带 {@code ROLE_} 前缀
     * @return 创建后的用户，含服务端生成的公开 ID
     */
    UserAccount create(String username, String passwordHash, List<String> roles);

    /**
     * 按公开 ID 查询可对外展示的用户资料。
     *
     * <p>返回对象不含口令摘要与内部主键，可直接用于 API 响应。</p>
     *
     * @param publicId 公开 ID（UUID 字符串）
     * @return 命中的资料；不存在时返回空
     */
    Optional<UserProfile> findProfileByPublicId(String publicId);

    /**
     * 更新可编辑的资料字段，并把 {@code updated_at} 刷新为当前时间。
     *
     * <p>空串必须由调用方归一化为 {@code null} 后再传入：{@code email} 有唯一约束，
     * 多个空串会互相冲突。</p>
     *
     * @param publicId    公开 ID
     * @param displayName 展示名，可为 {@code null}
     * @param email       邮箱，可为 {@code null}
     * @param bio         个人简介，可为 {@code null}
     */
    void updateProfile(String publicId, String displayName, String email, String bio);

    /**
     * 替换口令摘要，并把 {@code updated_at} 刷新为当前时间。
     *
     * <p>调用方负责编码（BCrypt）与旧口令校验；本方法只落库，不感知明文口令。</p>
     *
     * @param publicId     公开 ID
     * @param passwordHash 新的口令摘要
     */
    void updatePasswordHash(String publicId, String passwordHash);

    /**
     * 统计符合过滤条件的用户数，供管理端分页查询使用。
     *
     * @param keyword 登录名或邮箱的原始匹配串（已去首尾空白，{@code null} 表示不过滤）；
     *                {@code LIKE} 通配符由实现负责拼接
     * @param status  账号状态，{@code null} 表示不过滤
     * @return 命中条数
     */
    long countUsers(String keyword, UserStatus status);

    /**
     * 分页查询用户资料，按创建时间倒序。
     *
     * @param keyword 登录名或邮箱的原始匹配串（已去首尾空白，{@code null} 表示不过滤）；
     *                {@code LIKE} 通配符由实现负责拼接
     * @param status  账号状态，{@code null} 表示不过滤
     * @param offset  偏移量
     * @param size    每页条数
     * @return 当前页的用户资料，不含口令摘要与内部主键
     */
    List<UserProfile> listUsers(String keyword, UserStatus status, long offset, int size);

    /**
     * 更新账号状态，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId 公开 ID
     * @param status   目标状态
     * @return 影响行数；0 表示用户已不存在
     */
    int updateStatus(String publicId, UserStatus status);

    /**
     * 替换账号角色，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId 公开 ID
     * @param roles    业务角色，已去重且不带 {@code ROLE_} 前缀
     * @return 影响行数；0 表示用户已不存在
     */
    int updateRoles(String publicId, List<String> roles);

    /**
     * 统计启用状态的管理员数量。
     *
     * <p>管理端移除管理员角色前用它兜底，避免系统失去最后一个可用的管理员。</p>
     *
     * @return 启用状态且角色含 {@code ADMIN} 的用户数
     */
    long countActiveAdmins();
}
