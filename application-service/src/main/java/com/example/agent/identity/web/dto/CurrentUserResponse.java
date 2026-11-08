package com.example.agent.identity.web.dto;

import java.util.List;

/**
 * 当前登录用户信息，供前端在登录后或刷新页面时恢复用户态。
 *
 * @param publicId 对外公开 ID（UUID），前端只保存该值，任何场景都不使用内部自增主键
 * @param username 登录名
 * @param roles    角色名列表，已去掉 {@code ROLE_} 前缀
 */
public record CurrentUserResponse(String publicId, String username, List<String> roles) {
}
