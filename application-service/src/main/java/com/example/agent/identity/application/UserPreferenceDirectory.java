package com.example.agent.identity.application;

import com.example.agent.identity.domain.UserPreference;
import java.util.Optional;

/**
 * 用户偏好的数据访问端口。
 *
 * <p>与 {@link UserDirectory} 一样用端口隔离存储：生产实现走 MyBatis + PostgreSQL，
 * 测试可替换为内存实现。查询按 {@code users.public_id} 关联，内部自增主键不出接口层。</p>
 */
public interface UserPreferenceDirectory {

    /**
     * 按用户公开 ID 查询偏好。
     *
     * @param publicId 公开 ID（UUID 字符串）
     * @return 命中的偏好；用户存在但从未保存过、或用户不存在时都返回空，
     *         调用方以 {@link UserPreference#defaults()} 作为回退
     */
    Optional<UserPreference> findByPublicId(String publicId);

    /**
     * 写入偏好：不存在则新增，存在则整行覆盖。
     *
     * @param publicId   公开 ID
     * @param preference 偏好值；{@code updatedAt} 被忽略，由数据库统一写入 {@code now()}
     * @return {@code true} 表示用户存在且写入成功；{@code false} 表示用户已不存在，
     *         没有任何行被写入
     */
    boolean upsert(String publicId, UserPreference preference);
}
