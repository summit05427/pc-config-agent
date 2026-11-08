package com.example.agent.identity.web.dto;

import java.time.Instant;
import java.util.List;

/**
 * 管理端用户摘要。
 *
 * <p>只包含公开字段：内部自增主键、口令摘要、资料中的 bio 与更新时间都不下发。</p>
 *
 * @param publicId  对外公开 ID
 * @param username  登录名
 * @param email     邮箱，{@code null} 表示未设置
 * @param roles     业务角色，不带 {@code ROLE_} 前缀
 * @param status    账号状态
 * @param createdAt 创建时间（UTC）
 */
public record AdminUserSummaryResponse(
        String publicId,
        String username,
        String email,
        List<String> roles,
        String status,
        Instant createdAt) {
}
