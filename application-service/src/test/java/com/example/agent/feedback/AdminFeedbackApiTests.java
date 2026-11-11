package com.example.agent.feedback;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.support.InMemoryMessageFeedbackMapper;
import com.example.agent.support.InMemoryMessageFeedbackMapperConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 管理端反馈接口集成测试。
 *
 * <p>覆盖点：分页与筛选、统计口径、CSV 导出（含公式注入防护）、非管理员拒绝。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryMessageFeedbackMapperConfig.class
})
class AdminFeedbackApiTests {

    private static final String FEEDBACK_PATH = "/api/v1/admin/feedback";
    private static final String LOGIN_PATH = "/api/v1/auth/login";

    private final MockMvc mockMvc;
    private final UserDirectory userDirectory;
    private final InMemoryMessageFeedbackMapper feedbackMapper;

    @Autowired
    AdminFeedbackApiTests(
            MockMvc mockMvc, UserDirectory userDirectory, InMemoryMessageFeedbackMapper feedbackMapper) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.feedbackMapper = feedbackMapper;
    }

    @BeforeEach
    void setUp() {
        feedbackMapper.clear();
        // 模拟管理端 SQL 的 LEFT JOIN users：登录名来自用户目录，而不是反馈表
        userDirectory.findByUsername("demo").ifPresent(account ->
                feedbackMapper.registerUsername(account.publicId(), account.username()));
    }

    @Test
    void listFeedback_shouldReturnUsernameAndRating() throws Exception {
        upsertAsDemo("t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"INACCURATE","comment":"价格不对"}
                """);

        mockMvc.perform(get(FEEDBACK_PATH).header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.list[0].username").value("demo"))
                .andExpect(jsonPath("$.data.list[0].messageId").value("t-1:3"))
                .andExpect(jsonPath("$.data.list[0].rating").value("DOWN"))
                .andExpect(jsonPath("$.data.list[0].reasonCode").value("INACCURATE"));
    }

    @Test
    void listFeedback_shouldFilterByRatingAndPaginate() throws Exception {
        upsertAsDemo("t-1:1", """
                {"threadId":"t-1","rating":"UP"}
                """);
        upsertAsDemo("t-1:2", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"FORMAT"}
                """);
        upsertAsDemo("t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"OFF_TOPIC"}
                """);

        mockMvc.perform(get(FEEDBACK_PATH)
                        .param("rating", "DOWN")
                        .param("page", "1")
                        .param("size", "1")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(2))
                .andExpect(jsonPath("$.data.list.length()").value(1));
    }

    @Test
    void listFeedback_shouldRejectUnknownReasonFilter() throws Exception {
        mockMvc.perform(get(FEEDBACK_PATH)
                        .param("reasonCode", "WHATEVER")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void summarize_shouldReturnCountsAndReasonLabels() throws Exception {
        upsertAsDemo("t-1:1", """
                {"threadId":"t-1","rating":"UP"}
                """);
        upsertAsDemo("t-1:2", """
                {"threadId":"t-1","rating":"UP"}
                """);
        upsertAsDemo("t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"OFF_TOPIC"}
                """);

        mockMvc.perform(get(FEEDBACK_PATH + "/summary").header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.upCount").value(2))
                .andExpect(jsonPath("$.data.downCount").value(1))
                .andExpect(jsonPath("$.data.reasons[0].reasonCode").value("OFF_TOPIC"))
                .andExpect(jsonPath("$.data.reasons[0].label").value("答非所问"))
                .andExpect(jsonPath("$.data.reasons[0].total").value(1));
    }

    @Test
    void export_shouldReturnCsvWithBomAndGuardFormula() throws Exception {
        upsertAsDemo("t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"INACCURATE","comment":"=1+1"}
                """);

        mockMvc.perform(get(FEEDBACK_PATH + "/export").header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CONTENT_DISPOSITION, containsString("attachment")))
                .andExpect(content().contentTypeCompatibleWith("text/csv"))
                .andExpect(content().string(containsString("消息ID")))
                .andExpect(content().string(containsString("踩")))
                .andExpect(content().string(containsString("信息不准确")))
                // 用户备注以 = 开头，导出时必须加前缀，避免表格软件当公式执行
                .andExpect(content().string(containsString("'=1+1")));
    }

    @Test
    void listFeedback_shouldForbidNonAdmin() throws Exception {
        mockMvc.perform(get(FEEDBACK_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(20002));
    }

    private void upsertAsDemo(String messageId, String body) throws Exception {
        mockMvc.perform(put("/api/v1/messages/" + messageId + "/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());
    }

    private String adminToken() throws Exception {
        return token("admin", "test-only-password");
    }

    private String token(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"%s"}
                                """.formatted(username, password)))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + accessToken;
    }
}
