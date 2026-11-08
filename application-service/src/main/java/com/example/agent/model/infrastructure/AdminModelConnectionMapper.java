package com.example.agent.model.infrastructure;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 管理端模型连接只读数据访问，SQL 见 {@code mapper/model/AdminModelConnectionMapper.xml}。
 *
 * <p>与用户侧 Mapper 分开：管理端需要看全部用户的连接，但绝不提供写入方法，
 * 避免管理端误改用户凭证。</p>
 */
@Mapper
public interface AdminModelConnectionMapper {

    /**
     * 统计满足条件的连接数。
     *
     * @param filter 查询条件
     * @return 连接条数
     */
    long count(@Param("filter") AdminConnectionFilter filter);

    /**
     * 分页查询连接与当前有效凭证摘要。
     *
     * @param filter 查询条件
     * @param offset 跳过条数
     * @param limit  每页条数
     * @return 连接只读行
     */
    List<AdminConnectionRow> findPage(
            @Param("filter") AdminConnectionFilter filter,
            @Param("offset") long offset,
            @Param("limit") int limit);
}
