package com.example.agent.shared.mybatis;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;

/**
 * PostgreSQL {@code uuid} 列与 {@link UUID} 之间的类型转换。
 *
 * <p>MyBatis 3.5.x 没有内置 UUID 处理器，未注册时 resultMap 里声明
 * {@code javaType=java.util.UUID} 会直接抛 “No typehandler found”。注册后
 * 行对象与 Mapper 入参都能直接使用 {@link UUID}，不必在每个 SQL 里把 UUID
 * 转成字符串再补 {@code ::uuid} 强转。</p>
 */
public class UuidTypeHandler extends BaseTypeHandler<UUID> {

    @Override
    public void setNonNullParameter(PreparedStatement statement, int index, UUID parameter, JdbcType jdbcType)
            throws SQLException {
        // 直接传 UUID 对象，由 PostgreSQL 驱动按 uuid 类型绑定，避免被当成 VARCHAR 拒绝
        statement.setObject(index, parameter);
    }

    @Override
    public UUID getNullableResult(ResultSet resultSet, String columnName) throws SQLException {
        return resultSet.getObject(columnName, UUID.class);
    }

    @Override
    public UUID getNullableResult(ResultSet resultSet, int columnIndex) throws SQLException {
        return resultSet.getObject(columnIndex, UUID.class);
    }

    @Override
    public UUID getNullableResult(CallableStatement statement, int columnIndex) throws SQLException {
        return statement.getObject(columnIndex, UUID.class);
    }
}
