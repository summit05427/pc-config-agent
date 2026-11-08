package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.IdentityErrorCode;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.identity.web.dto.UserPasswordChangeRequest;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 修改口令服务。
 *
 * <p>校验、替换摘要与撤销其他设备必须在同一事务里完成：只改摘要不撤会话会让
 * 旧设备继续凭已轮换的刷新令牌长期在线；只撤会话不改摘要则用户下次仍能用旧口令登录。</p>
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class UserPasswordService {

    private final UserDirectory userDirectory;
    private final PasswordEncoder passwordEncoder;
    private final RefreshSessionService refreshSessionService;
    private final AuthAuditRecorder authAuditRecorder;

    /**
     * 修改当前登录用户的口令，并撤销其他设备的刷新会话。
     *
     * @param publicId        令牌 {@code sub}，即 {@code users.public_id}
     * @param currentFamilyId 令牌 {@code sid}，即当前设备所在令牌族，可为 {@code null}
     * @param request         已通过 Bean Validation 的请求体
     * @throws BusinessException 用户已不存在或令牌缺少 {@code sid}（{@code UNAUTHORIZED}）、
     *                           当前口令不正确（{@code 40102}）、新旧口令相同（{@code 40103}）
     */
    @Transactional
    public void changePassword(String publicId, String currentFamilyId, UserPasswordChangeRequest request) {
        UserAccount account = userDirectory.findByPublicId(publicId)
                .orElseThrow(() -> new BusinessException(
                        CommonErrorCode.UNAUTHORIZED, CommonErrorCode.UNAUTHORIZED.message()));
        if (currentFamilyId == null || currentFamilyId.isBlank()) {
            // 改造前签发的存量令牌没有 sid（最长 10 分钟即过期），无法区分「当前设备」，
            // 因此直接要求重新登录，避免误把当前设备一起踢下线
            throw new BusinessException(CommonErrorCode.UNAUTHORIZED, "登录状态已失效，请重新登录");
        }
        if (!passwordEncoder.matches(request.currentPassword(), account.passwordHash())) {
            // 只记录用户名与失败原因，绝不记录口令或摘要
            log.warn("修改口令失败：当前口令不正确 username={}", account.username());
            throw new BusinessException(IdentityErrorCode.CURRENT_PASSWORD_INVALID);
        }
        if (passwordEncoder.matches(request.newPassword(), account.passwordHash())) {
            throw new BusinessException(IdentityErrorCode.PASSWORD_UNCHANGED);
        }
        userDirectory.updatePasswordHash(publicId, passwordEncoder.encode(request.newPassword()));
        int revokedSessions = refreshSessionService.revokeAllExceptFamily(
                account.id(), UUID.fromString(currentFamilyId));
        // 改密是高风险操作：审计在事务内调用，但以独立事务提交，业务回滚不影响事件留痕
        authAuditRecorder.record(AuthAuditEvent.PASSWORD_CHANGE, account.username(), account.publicId());
        log.info("修改口令成功 username={} revokedOtherSessions={}", account.username(), revokedSessions);
    }
}
