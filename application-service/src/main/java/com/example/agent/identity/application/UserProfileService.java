package com.example.agent.identity.application;

import com.example.agent.identity.domain.IdentityErrorCode;
import com.example.agent.identity.domain.UserProfile;
import com.example.agent.identity.web.dto.UserProfileResponse;
import com.example.agent.identity.web.dto.UserProfileUpdateRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 个人资料读写服务。
 *
 * <p>只处理「展示名 / 邮箱 / 简介」这三个可编辑字段；登录名与角色由管理端维护，
 * 不在本服务职责内。</p>
 */
@Service
@RequiredArgsConstructor
public class UserProfileService {

    private final UserDirectory userDirectory;

    /**
     * 查询当前登录用户的资料。
     *
     * @param publicId 令牌 {@code sub}，即 {@code users.public_id}
     * @return 对外资料视图
     * @throws BusinessException 用户已不存在时抛 {@link CommonErrorCode#UNAUTHORIZED}，
     *                           使前端按「登录已失效」处理
     */
    @Transactional(readOnly = true)
    public UserProfileResponse getProfile(String publicId) {
        return toResponse(requireProfile(publicId));
    }

    /**
     * 更新当前登录用户的资料并返回最新值。
     *
     * @param publicId 令牌 {@code sub}
     * @param request  已通过 Bean Validation 的请求体
     * @return 更新后的资料
     * @throws BusinessException 展示名为空白（{@code PARAM_INVALID}）、用户已不存在
     *                           （{@code UNAUTHORIZED}）或邮箱与他人冲突（{@code EMAIL_TAKEN}）
     */
    @Transactional
    public UserProfileResponse updateProfile(String publicId, UserProfileUpdateRequest request) {
        requireProfile(publicId);
        // DTO 已在构造时归一化；这里再守一次，防止内部调用绕过 Bean Validation 时写入空展示名
        String displayName = request.displayName();
        if (displayName == null || displayName.isBlank()) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "展示名不能为空");
        }
        try {
            userDirectory.updateProfile(publicId, displayName, request.email(), request.bio());
        } catch (DataIntegrityViolationException exception) {
            // 唯一约束只有 email 一处可触发；这里不记录堆栈，避免把 SQL 细节写进日志
            throw new BusinessException(IdentityErrorCode.EMAIL_TAKEN);
        }
        return toResponse(requireProfile(publicId));
    }

    private UserProfile requireProfile(String publicId) {
        return userDirectory
                .findProfileByPublicId(publicId)
                .orElseThrow(() -> new BusinessException(
                        CommonErrorCode.UNAUTHORIZED, CommonErrorCode.UNAUTHORIZED.message()));
    }

    private static UserProfileResponse toResponse(UserProfile profile) {
        return new UserProfileResponse(
                profile.publicId(),
                profile.username(),
                profile.displayName(),
                profile.email(),
                profile.bio(),
                profile.roles(),
                profile.status().name(),
                profile.createdAt(),
                profile.updatedAt());
    }
}
