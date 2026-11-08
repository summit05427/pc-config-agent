package com.example.agent.pcbuild.infrastructure;

import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 方案快照 Mapper。
 */
@Mapper
public interface BuildSnapshotMapper {

    /**
     * @param row 待插入行
     * @return 影响行数
     */
    int insert(BuildSnapshotRow row);

    /**
     * @param buildId 快照标识
     * @param userId  所属用户
     * @return 命中行；不存在或归属不符时为空
     */
    BuildSnapshotRow findByIdAndUserId(@Param("buildId") UUID buildId, @Param("userId") UUID userId);
}
