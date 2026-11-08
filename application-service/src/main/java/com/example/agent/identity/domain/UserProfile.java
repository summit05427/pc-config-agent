package com.example.agent.identity.domain;

import java.time.Instant;
import java.util.List;

/**
 * 用户资料视图对象。
 *
 * <p>与 {@link UserAccount} 的差别在于：这里只包含可以对外展示的字段，
 * 不含口令摘要与内部自增主键，因此可以直接转换成交付给前端的响应。</p>
 *
 * @param publicId    对外公开 ID（UUID）
 * @param username    登录名，不允许修改
 * @param displayName 展示名，{@code null} 表示未设置
 * @param email       邮箱，{@code null} 表示未设置
 * @param bio         个人简介，{@code null} 表示未设置
 * @param roles       业务角色，已去掉 {@code ROLE_} 前缀
 * @param status      账号状态
 * @param createdAt   创建时间（UTC）
 * @param updatedAt   最后更新时间（UTC）
 */
public record UserProfile(
        String publicId,
        String username,
        String displayName,
        String email,
        String bio,
        List<String> roles,
        UserStatus status,
        Instant createdAt,
        Instant updatedAt) {
}
