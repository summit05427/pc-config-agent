package com.example.agent.model.application;

import com.example.agent.model.infrastructure.AdminConnectionFilter;
import com.example.agent.model.infrastructure.AdminModelConnectionMapper;
import com.example.agent.model.web.dto.AdminModelConnectionQuery;
import com.example.agent.model.web.dto.AdminModelConnectionResponse;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 管理端模型连接只读查询服务。
 *
 * <p>管理端只能观察用户的 Provider 连接状态，不能创建、修改或删除用户凭证；
 * 响应只含凭证掩码与状态，密文与明文都不进入查询结果。</p>
 */
@Service
@RequiredArgsConstructor
public class AdminModelConnectionService {

    private final AdminModelConnectionMapper adminModelConnectionMapper;

    /**
     * 分页查询全部用户的模型连接。
     *
     * @param query 查询参数，空串按「不过滤」处理
     * @return 连接只读分页，按创建时间倒序
     * @throws BusinessException 用户标识格式非法
     */
    @Transactional(readOnly = true)
    public PageResult<AdminModelConnectionResponse> list(AdminModelConnectionQuery query) {
        AdminConnectionFilter filter = new AdminConnectionFilter(
                parseUserId(query.getUserId()),
                blankToNull(query.getProvider()),
                blankToNull(query.getStatus()));
        long total = adminModelConnectionMapper.count(filter);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminModelConnectionResponse> list = adminModelConnectionMapper
                .findPage(filter, query.offset(), query.getSize()).stream()
                .map(AdminModelConnectionResponse::from)
                .toList();
        return PageResult.of(list, total, query);
    }

    /** 用户标识来自查询参数，先校验格式再交给 SQL，避免非法 UUID 变成 500。 */
    private static UUID parseUserId(String rawUserId) {
        String userId = blankToNull(rawUserId);
        if (userId == null) {
            return null;
        }
        try {
            return UUID.fromString(userId);
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "用户标识格式不正确");
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
