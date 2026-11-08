package com.example.agent.identity.infrastructure;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * {@code auth_audit_logs} 表数据访问接口，SQL 定义见
 * {@code mapper/identity/AuthAuditLogMapper.xml}。
 *
 * <p>{@code user_id} 由 SQL 按公开 ID 或登录名回查，调用方无需先解析内部主键；
 * 用户不存在时该列写 {@code NULL}，审计记录仍然保留。</p>
 */
@Mapper
public interface AuthAuditLogMapper {

    /**
     * 追加一条审计记录。
     *
     * @param username  登录名
     * @param publicId  用户公开 ID，可为 {@code null}
     * @param event     事件标识
     * @param ip        客户端 IP，可为 {@code null}
     * @param userAgent 客户端 User-Agent，可为 {@code null}
     * @param requestId 请求 ID，可为 {@code null}
     * @return 影响行数
     */
    int insert(
            @Param("username") String username,
            @Param("publicId") String publicId,
            @Param("event") String event,
            @Param("ip") String ip,
            @Param("userAgent") String userAgent,
            @Param("requestId") String requestId);

    /**
     * 统计符合过滤条件的审计记录数。
     *
     * @param event    事件标识，可为 {@code null}
     * @param username 登录名精确匹配，可为 {@code null}
     * @return 命中条数
     */
    long countPage(@Param("event") String event, @Param("username") String username);

    /**
     * 按发生时间倒序分页查询审计记录。
     *
     * @param event    事件标识，可为 {@code null}
     * @param username 登录名精确匹配，可为 {@code null}
     * @param offset   偏移量
     * @param size     每页条数
     * @return 当前页记录
     */
    List<AuthAuditLogRow> selectPage(
            @Param("event") String event,
            @Param("username") String username,
            @Param("offset") long offset,
            @Param("size") int size);
}
