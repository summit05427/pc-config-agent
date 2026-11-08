package com.example.agent.identity.web.dto;

import java.time.Instant;
import java.util.List;

/**
 * 个人资料响应。
 *
 * <p>只包含可对外展示的字段：不出现内部自增主键与口令摘要。</p>
 *
 * @param publicId    对外公开 ID（UUID），与令牌 {@code sub} 一致
 * @param username    登录名，不可修改
 * @param displayName 展示名，{@code null} 表示未设置
 * @param email       邮箱，{@code null} 表示未设置
 * @param bio         个人简介，{@code null} 表示未设置
 * @param roles       角色名列表，已去掉 {@code ROLE_} 前缀
 * @param status      账号状态，如 {@code ACTIVE}
 * @param createdAt   创建时间（ISO-8601）
 * @param updatedAt   最后更新时间（ISO-8601）
 */
public record UserProfileResponse(
        String publicId,
        String username,
        String displayName,
        String email,
        String bio,
        List<String> roles,
        String status,
        Instant createdAt,
        Instant updatedAt) {
}
