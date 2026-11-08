package com.example.agent;

import com.example.agent.support.InMemoryUserDirectoryConfig;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@Import(InMemoryUserDirectoryConfig.class)
class AgentApplicationServiceApplicationTests {

    @Test
    void contextLoads() {
    }

}
