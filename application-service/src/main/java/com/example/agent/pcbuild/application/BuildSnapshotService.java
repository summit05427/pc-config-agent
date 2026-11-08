package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.shared.error.BusinessException;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 方案快照服务。
 *
 * <p>写入只发生在求解成功后的同一事务内；读取必须同时匹配 {@code build_id} 与
 * {@code user_id}，不属于当前用户的快照统一按 404 处理，不泄露存在性。</p>
 */
@Service
@RequiredArgsConstructor
public class BuildSnapshotService {

    private final BuildSnapshotRepository repository;

    private final BuildResultFactory factory;

    /**
     * @param result 已落库前结果
     */
    public void save(BuildResult result) {
        repository.save(factory.toSnapshot(result));
    }

    /**
     * 读取当前用户拥有的快照。
     *
     * @param userId  用户公开 ID
     * @param buildId 快照标识
     * @return 响应
     * @throws BusinessException 不存在或归属不符时 404 {@code 40302}
     */
    public BuildResultResponse requireOwned(UUID userId, UUID buildId) {
        BuildSnapshot snapshot = repository.findByIdAndUserId(buildId, userId)
                .orElseThrow(() -> new BusinessException(PcBuildErrorCode.BUILD_NOT_FOUND));
        return factory.fromSnapshot(snapshot);
    }
}
