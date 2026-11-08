package com.example.agent.identity.infrastructure;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * {@code user_preferences} 表数据访问接口，SQL 定义见
 * {@code mapper/identity/UserPreferenceMapper.xml}。
 *
 * <p>查询与写入都通过 {@code users.public_id} 关联，调用方无需先查内部主键；
 * 字段显式列出且全部参数化。</p>
 */
@Mapper
public interface UserPreferenceMapper {

    /**
     * 按用户公开 ID 查询偏好。
     *
     * @param publicId 对外公开 ID
     * @return 命中的行；用户不存在或从未保存过偏好时返回 {@code null}
     */
    UserPreferenceRow findByPublicId(@Param("publicId") String publicId);

    /**
     * 新增或整行覆盖偏好，并把 {@code updated_at} 刷新为当前时间。
     *
     * <p>用 {@code INSERT ... SELECT FROM users} 解析内部主键：用户不存在时插入 0 行，
     * 调用方据此识别「令牌有效但用户已被删除」。</p>
     *
     * @param publicId     对外公开 ID
     * @param instructions 自定义指令，可为 {@code null}
     * @param replyLanguage 回复语言取值
     * @param responseStyle 回复风格取值
     * @param useHistory   是否使用历史上下文
     * @return 影响行数；0 表示用户已不存在
     */
    int upsert(
            @Param("publicId") String publicId,
            @Param("instructions") String instructions,
            @Param("replyLanguage") String replyLanguage,
            @Param("responseStyle") String responseStyle,
            @Param("useHistory") boolean useHistory);
}
