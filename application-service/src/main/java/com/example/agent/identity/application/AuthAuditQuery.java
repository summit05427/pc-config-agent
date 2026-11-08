package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditLogItem;
import java.util.List;

/**
 * 认证审计的只读查询端口。
 *
 * <p>与写入端口 {@link AuthAuditLog} 分开：写入走独立事务且必须容错，
 * 查询是管理端同步读取，两者失败语义完全不同。</p>
 */
public interface AuthAuditQuery {

    /**
     * 统计符合过滤条件的审计记录数。
     *
     * @param event    事件标识，{@code null} 表示不过滤
     * @param username 登录名精确匹配，{@code null} 表示不过滤
     * @return 命中条数
     */
    long count(String event, String username);

    /**
     * 按发生时间倒序分页查询审计记录。
     *
     * @param event    事件标识，{@code null} 表示不过滤
     * @param username 登录名精确匹配，{@code null} 表示不过滤
     * @param offset   偏移量
     * @param size     每页条数
     * @return 当前页的审计记录
     */
    List<AuthAuditLogItem> findPage(String event, String username, long offset, int size);
}
