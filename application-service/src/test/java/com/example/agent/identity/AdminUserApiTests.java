package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.support.InMemoryAuthAuditLog;
import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryAuthAuditQueryConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 管理端用户接口集成测试：走完整安全过滤器链，用户源与审计写入为内存实现。
 *
 * <p>覆盖成功、参数非法、目标不存在、无权限与业务冲突分支。
 * 共享的 Spring 容器会被多个测试类复用，因此用例只操作自己创建的用户，
 * 角色提升后必须恢复，避免影响「最后一个管理员」约束。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class,
        InMemoryAuthAuditQueryConfig.class
})
class AdminUserApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String USERS_PATH = "/api/v1/admin/users";
    private static final String ADMIN_USERNAME = "admin";
    private static final String ADMIN_PASSWORD = "test-only-password";

    private final MockMvc mockMvc;
    private final UserDirectory userDirectory;
    private final PasswordEncoder passwordEncoder;
    private final InMemoryAuthAuditLog auditLog;

    @Autowired
    AdminUserApiTests(
            MockMvc mockMvc,
            UserDirectory userDirectory,
            PasswordEncoder passwordEncoder,
            InMemoryAuthAuditLog auditLog) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.passwordEncoder = passwordEncoder;
        this.auditLog = auditLog;
    }

    @BeforeEach
    void clearAuditLog() {
        auditLog.clear();
    }

    @Test
    void listUsers_shouldReturnPageWithPublicFieldsOnly() throws Exception {
        mockMvc.perform(get(USERS_PATH)
                        .param("page", "1")
                        .param("size", "5")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.page").value(1))
                .andExpect(jsonPath("$.data.size").value(5))
                // 首页至少包含 bootstrap 的 admin 与 demo 两个账号
                .andExpect(jsonPath("$.data.total").value(greaterThanOrEqualTo(2)))
                .andExpect(jsonPath("$.data.list[0].publicId").isNotEmpty())
                .andExpect(jsonPath("$.data.list[0].username").isNotEmpty())
                .andExpect(jsonPath("$.data.list[0].status").isNotEmpty())
                .andExpect(jsonPath("$.data.list[0].passwordHash").doesNotExist())
                .andExpect(jsonPath("$.data.list[0].id").doesNotExist());
    }

    @Test
    void listUsers_shouldFilterByKeyword() throws Exception {
        UserAccount target = createUser("admin-list-target", "target-password", List.of("USER"));

        mockMvc.perform(get(USERS_PATH)
                        .param("keyword", target.username())
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.list[0].username").value(target.username()));
    }

    @Test
    void listUsers_shouldRejectUnknownStatus() throws Exception {
        mockMvc.perform(get(USERS_PATH)
                        .param("status", "ARCHIVED")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void listUsers_shouldForbidNonAdmin() throws Exception {
        UserAccount account = createUser("admin-permission-user", "user-password", List.of("USER"));

        mockMvc.perform(get(USERS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, tokenFor(account.username(), "user-password")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(20002));
    }

    @Test
    void updateStatus_shouldReturnNotFound_whenUserMissing() throws Exception {
        mockMvc.perform(patch(USERS_PATH + "/" + UUID.randomUUID() + "/status")
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"DISABLED"}
                                """))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(30001));
    }

    @Test
    void updateStatus_shouldRejectUnknownStatusValue() throws Exception {
        UserAccount target = createUser("admin-status-invalid", "target-password", List.of("USER"));

        mockMvc.perform(patch(statusPath(target))
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"ARCHIVED"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void updateStatus_shouldRejectDisablingCurrentAdmin() throws Exception {
        String adminPublicId = userDirectory.findByUsername(ADMIN_USERNAME).orElseThrow().publicId();

        mockMvc.perform(patch(USERS_PATH + "/" + adminPublicId + "/status")
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"DISABLED"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(30002));
    }

    @Test
    void updateStatus_shouldDisableUserAndRecordAuditEvent() throws Exception {
        UserAccount target = createUser("admin-disable-target", "target-password", List.of("USER"));

        mockMvc.perform(patch(statusPath(target))
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"DISABLED"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("DISABLED"));

        assertThat(auditLog.findAll())
                .anyMatch(entry -> entry.event() == AuthAuditEvent.USER_DISABLED
                        && entry.username().equals(target.username()));
        // 禁用后该用户不能再登录
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(target.username(), "target-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void updateRoles_shouldRejectRoleOutsideWhitelist() throws Exception {
        UserAccount target = createUser("admin-role-invalid", "target-password", List.of("USER"));

        mockMvc.perform(patch(rolesPath(target))
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"roles":["SUPERADMIN"]}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void updateRoles_shouldChangeRolesAndRecordAuditEvent() throws Exception {
        UserAccount target = createUser("admin-role-target", "target-password", List.of("USER"));

        mockMvc.perform(patch(rolesPath(target))
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"roles":["USER","ADMIN"]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.roles[0]").value("USER"))
                .andExpect(jsonPath("$.data.roles[1]").value("ADMIN"));

        assertThat(auditLog.findAll())
                .anyMatch(entry -> entry.event() == AuthAuditEvent.ROLE_CHANGED
                        && entry.username().equals(target.username()));

        // 恢复为普通用户，避免影响「最后一个启用管理员」约束
        mockMvc.perform(patch(rolesPath(target))
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"roles":["USER"]}
                                """))
                .andExpect(status().isOk());
    }

    @Test
    void updateRoles_shouldRejectRemovingLastActiveAdmin() throws Exception {
        String adminPublicId = userDirectory.findByUsername(ADMIN_USERNAME).orElseThrow().publicId();

        mockMvc.perform(patch(USERS_PATH + "/" + adminPublicId + "/roles")
                        .header(HttpHeaders.AUTHORIZATION, adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"roles":["USER"]}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(30002));
    }

    private String statusPath(UserAccount account) {
        return USERS_PATH + "/" + account.publicId() + "/status";
    }

    private String rolesPath(UserAccount account) {
        return USERS_PATH + "/" + account.publicId() + "/roles";
    }

    private UserAccount createUser(String username, String rawPassword, List<String> roles) {
        return userDirectory.create(username, passwordEncoder.encode(rawPassword), roles);
    }

    private String adminToken() throws Exception {
        return tokenFor(ADMIN_USERNAME, ADMIN_PASSWORD);
    }

    private String tokenFor(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, password)))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + accessToken;
    }

    private static String loginBody(String username, String password) {
        return """
                {"username":"%s","password":"%s"}
                """.formatted(username, password);
    }
}
