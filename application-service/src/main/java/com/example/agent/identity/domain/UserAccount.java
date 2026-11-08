package com.example.agent.identity.domain;

import java.util.List;

/**
 * 用户领域对象。
 *
 * @param id           内部自增主键，只在服务端内部使用，禁止写入 Token、响应或 URL
 * @param publicId     对外唯一标识（UUID），JWT 的 {@code sub} 取自该字段
 * @param username     登录名
 * @param passwordHash 口令摘要，第三方登录用户可能为空
 * @param roles        业务角色，大写且不带 {@code ROLE_} 前缀
 * @param status       账号状态
 */
public record UserAccount(
        Long id,
        String publicId,
        String username,
        String passwordHash,
        List<String> roles,
        UserStatus status) {
}
