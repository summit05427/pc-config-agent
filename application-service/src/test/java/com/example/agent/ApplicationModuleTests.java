package com.example.agent;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleTests {

    @Test
    void moduleStructureShouldSatisfyDependencyRules() {
        ApplicationModules.of(AgentApplicationServiceApplication.class).verify();
    }
}
