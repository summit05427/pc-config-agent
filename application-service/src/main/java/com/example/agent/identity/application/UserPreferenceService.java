package com.example.agent.identity.application;

import com.example.agent.identity.domain.ReplyLanguage;
import com.example.agent.identity.domain.ResponseStyle;
import com.example.agent.identity.domain.UserPreference;
import com.example.agent.identity.web.dto.UserPreferenceResponse;
import com.example.agent.identity.web.dto.UserPreferenceUpdateRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 用户偏好读写服务。
 *
 * <p>偏好只是「用户声明」，不参与鉴权：本服务只保证长度与枚举合法，
 * 不据此放宽任何授权，也不把偏好写进令牌或权限判断。</p>
 */
@Service
@RequiredArgsConstructor
public class UserPreferenceService {

    private static final String USE_HISTORY_REQUIRED_MESSAGE = "是否使用历史上下文不能为空";

    private final UserPreferenceDirectory userPreferenceDirectory;

    /**
     * 查询当前登录用户的偏好。
     *
     * @param publicId 令牌 {@code sub}，即 {@code users.public_id}
     * @return 已保存的偏好；从未保存时返回默认值（{@code updatedAt} 为 {@code null}）
     */
    @Transactional(readOnly = true)
    public UserPreferenceResponse getPreferences(String publicId) {
        return toResponse(userPreferenceDirectory.findByPublicId(publicId).orElseGet(UserPreference::defaults));
    }

    /**
     * 全量保存当前登录用户的偏好并返回最新值。
     *
     * @param publicId 令牌 {@code sub}
     * @param request  已通过 Bean Validation 的请求体
     * @return 数据库中最新的偏好
     * @throws BusinessException 枚举或 {@code useHistory} 缺失（{@code PARAM_INVALID}）时，
     *                           或令牌有效但用户已被删除（{@code UNAUTHORIZED}）时
     */
    @Transactional
    public UserPreferenceResponse updatePreferences(String publicId, UserPreferenceUpdateRequest request) {
        Boolean useHistory = request.useHistory();
        // DTO 已用 @NotNull 拦一次；这里再守一次，防止内部调用绕过 Bean Validation 时 NPE
        if (useHistory == null) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, USE_HISTORY_REQUIRED_MESSAGE);
        }
        UserPreference preference = new UserPreference(
                request.instructions(),
                ReplyLanguage.fromWireValue(request.replyLanguage()),
                ResponseStyle.fromWireValue(request.responseStyle()),
                useHistory,
                // updatedAt 由数据库写入 now()，这里传 null 表示「尚未落库」
                null);
        if (!userPreferenceDirectory.upsert(publicId, preference)) {
            throw new BusinessException(CommonErrorCode.UNAUTHORIZED, CommonErrorCode.UNAUTHORIZED.message());
        }
        return toResponse(userPreferenceDirectory.findByPublicId(publicId).orElseGet(UserPreference::defaults));
    }

    private static UserPreferenceResponse toResponse(UserPreference preference) {
        return new UserPreferenceResponse(
                preference.instructions(),
                preference.replyLanguage().wireValue(),
                preference.responseStyle().wireValue(),
                preference.useHistory(),
                preference.updatedAt());
    }
}
