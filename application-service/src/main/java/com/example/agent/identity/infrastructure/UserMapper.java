package com.example.agent.identity.infrastructure;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * {@code users} 表数据访问接口，SQL 定义见 {@code mapper/identity/UserMapper.xml}。
 *
 * <p>查询字段显式列出且全部参数化；对外主键只走 {@code public_id}，内部自增主键仅限本服务使用。</p>
 */
@Mapper
public interface UserMapper {

    UserRow findByUsername(@Param("username") String username);

    UserRow findByPublicId(@Param("publicId") String publicId);

    UserRow findById(@Param("id") Long id);

    /**
     * 插入用户并回填自增主键。
     *
     * @param row 待插入行，成功后 {@code id} 被回填
     * @return 影响行数
     */
    int insert(UserRow row);

    /**
     * 按公开 ID 更新可编辑的资料字段，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId    对外公开 ID
     * @param displayName 展示名，可为 {@code null}
     * @param email       邮箱，可为 {@code null}
     * @param bio         个人简介，可为 {@code null}
     * @return 影响行数；0 表示用户已不存在
     */
    int updateProfile(
            @Param("publicId") String publicId,
            @Param("displayName") String displayName,
            @Param("email") String email,
            @Param("bio") String bio);

    /**
     * 按公开 ID 替换口令摘要，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId     对外公开 ID
     * @param passwordHash 新的口令摘要
     * @return 影响行数；0 表示用户已不存在
     */
    int updatePasswordHash(
            @Param("publicId") String publicId,
            @Param("passwordHash") String passwordHash);

    /**
     * 统计符合管理端过滤条件的用户数。
     *
     * @param keyword 已包含通配符的模糊匹配串，可为 {@code null}
     * @param status  账号状态，可为 {@code null}
     * @return 命中条数
     */
    long countUsers(@Param("keyword") String keyword, @Param("status") String status);

    /**
     * 分页查询用户资料，按创建时间倒序。
     *
     * @param keyword 已包含通配符的模糊匹配串，可为 {@code null}
     * @param status  账号状态，可为 {@code null}
     * @param offset  偏移量
     * @param size    每页条数
     * @return 当前页的用户行
     */
    List<UserRow> listUsers(
            @Param("keyword") String keyword,
            @Param("status") String status,
            @Param("offset") long offset,
            @Param("size") int size);

    /**
     * 更新账号状态，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId 对外公开 ID
     * @param status   目标状态
     * @return 影响行数；0 表示用户已不存在
     */
    int updateStatus(@Param("publicId") String publicId, @Param("status") String status);

    /**
     * 替换账号角色，并把 {@code updated_at} 刷新为当前时间。
     *
     * @param publicId 对外公开 ID
     * @param roles    逗号分隔的角色文本
     * @return 影响行数；0 表示用户已不存在
     */
    int updateRoles(@Param("publicId") String publicId, @Param("roles") String roles);

    /**
     * 统计启用状态且角色含 {@code ADMIN} 的用户数。
     *
     * @return 启用管理员数量
     */
    long countActiveAdmins();
}
