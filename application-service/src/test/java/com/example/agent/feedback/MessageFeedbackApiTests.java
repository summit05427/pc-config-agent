package com.example.agent.feedback;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

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
 * 用户侧反馈接口集成测试。
 *
 * <p>覆盖点：覆盖式写入、取消、按会话恢复、跨用户不可见、标识与枚举校验。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryMessageFeedbackMapperConfig.class
})
class MessageFeedbackApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";

    private final MockMvc mockMvc;
    private final InMemoryMessageFeedbackMapper feedbackMapper;

    @Autowired
    MessageFeedbackApiTests(MockMvc mockMvc, InMemoryMessageFeedbackMapper feedbackMapper) {
        this.mockMvc = mockMvc;
        this.feedbackMapper = feedbackMapper;
    }

    @BeforeEach
    void clearFeedback() {
        feedbackMapper.clear();
    }

    @Test
    void upsertFeedback_shouldReturnUpRating() throws Exception {
        mockMvc.perform(put("/api/v1/messages/t-1:3/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"threadId":"t-1","rating":"UP"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.messageId").value("t-1:3"))
                .andExpect(jsonPath("$.data.rating").value("UP"));
    }

    @Test
    void upsertFeedback_shouldOverwritePreviousRating() throws Exception {
        String token = token("demo", "test-only-demo-password");
        upsert(token, "t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"OFF_TOPIC","comment":"答非所问"}
                """);
        upsert(token, "t-1:3", """
                {"threadId":"t-1","rating":"UP"}
                """);

        mockMvc.perform(get("/api/v1/feedback")
                        .param("threadId", "t-1")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(1))
                .andExpect(jsonPath("$.data[0].rating").value("UP"))
                // 改为点赞后，之前的原因与备注不再保留，避免污染原因分布
                .andExpect(jsonPath("$.data[0].reasonCode").doesNotExist());
    }

    @Test
    void listFeedback_shouldNotExposeOtherUsersFeedback() throws Exception {
        upsert(token("demo", "test-only-demo-password"), "t-1:3", """
                {"threadId":"t-1","rating":"DOWN","reasonCode":"INACCURATE"}
                """);

        mockMvc.perform(get("/api/v1/feedback")
                        .param("threadId", "t-1")
                        .header(HttpHeaders.AUTHORIZATION, token("admin", "test-only-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void deleteFeedback_shouldRemoveOwnFeedback() throws Exception {
        String token = token("demo", "test-only-demo-password");
        upsert(token, "t-2:7", """
                {"threadId":"t-2","rating":"DOWN","reasonCode":"OTHER"}
                """);

        mockMvc.perform(delete("/api/v1/messages/t-2:7/feedback").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0));

        mockMvc.perform(get("/api/v1/feedback")
                        .param("threadId", "t-2")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void deleteFeedback_shouldReturn404_whenFeedbackMissing() throws Exception {
        mockMvc.perform(delete("/api/v1/messages/t-9:1/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40402));
    }

    @Test
    void upsertFeedback_shouldRejectInvalidMessageId() throws Exception {
        mockMvc.perform(put("/api/v1/messages/bad!id/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"threadId":"t-1","rating":"UP"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40401));
    }

    @Test
    void upsertFeedback_shouldRejectUnknownRating() throws Exception {
        mockMvc.perform(put("/api/v1/messages/t-1:3/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"threadId":"t-1","rating":"MEH"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40403));
    }

    @Test
    void upsertFeedback_shouldRejectUnknownReason() throws Exception {
        mockMvc.perform(put("/api/v1/messages/t-1:3/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token("demo", "test-only-demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"threadId":"t-1","rating":"DOWN","reasonCode":"WHATEVER"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40404));
    }

    @Test
    void upsertFeedback_shouldRequireAuthentication() throws Exception {
        mockMvc.perform(put("/api/v1/messages/t-1:3/feedback")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"threadId":"t-1","rating":"UP"}
                                """))
                .andExpect(status().isUnauthorized());
    }

    private void upsert(String token, String messageId, String body) throws Exception {
        mockMvc.perform(put("/api/v1/messages/" + messageId + "/feedback")
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());
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
