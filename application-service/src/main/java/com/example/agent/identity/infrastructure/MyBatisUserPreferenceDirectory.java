package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.UserPreferenceDirectory;
import com.example.agent.identity.domain.ReplyLanguage;
import com.example.agent.identity.domain.ResponseStyle;
import com.example.agent.identity.domain.UserPreference;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * PostgreSQL 用户偏好仓储实现。
 *
 * <p>数据库只存枚举字符串，读写边界在这一层完成与领域枚举的转换；
 * 领域层不感知列名与存储格式。</p>
 */
@Component
@RequiredArgsConstructor
public class MyBatisUserPreferenceDirectory implements UserPreferenceDirectory {

    private final UserPreferenceMapper userPreferenceMapper;

    @Override
    public Optional<UserPreference> findByPublicId(String publicId) {
        return Optional.ofNullable(userPreferenceMapper.findByPublicId(publicId))
                .map(MyBatisUserPreferenceDirectory::toPreference);
    }

    @Override
    public boolean upsert(String publicId, UserPreference preference) {
        int affectedRows = userPreferenceMapper.upsert(
                publicId,
                preference.instructions(),
                preference.replyLanguage().wireValue(),
                preference.responseStyle().wireValue(),
                preference.useHistory());
        return affectedRows > 0;
    }

    private static UserPreference toPreference(UserPreferenceRow row) {
        return new UserPreference(
                row.getInstructions(),
                ReplyLanguage.fromWireValue(row.getReplyLanguage()),
                ResponseStyle.fromWireValue(row.getResponseStyle()),
                Boolean.TRUE.equals(row.getUseHistory()),
                row.getUpdatedAt());
    }
}
