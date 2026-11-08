package com.example.agent.model.infrastructure;

import java.util.UUID;

/**
 * 管理端连接只读查询条件。
 *
 * @param userId   用户公开 ID，可为空
 * @param provider Provider 代码，可为空
 * @param status   连接状态，可为空
 */
public record AdminConnectionFilter(UUID userId, String provider, String status) {
}
