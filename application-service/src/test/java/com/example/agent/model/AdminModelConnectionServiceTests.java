package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.AdminModelConnectionService;
import com.example.agent.model.infrastructure.AdminConnectionFilter;
import com.example.agent.model.infrastructure.AdminConnectionRow;
import com.example.agent.model.infrastructure.AdminModelConnectionMapper;
import com.example.agent.model.web.dto.AdminModelConnectionQuery;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 管理端模型连接只读服务单测：不启动容器，数据访问隔离。
 *
 * <p>覆盖分页映射、凭证摘要、空结果与用户标识校验；服务不提供任何写入路径。</p>
 */
@ExtendWith(MockitoExtension.class)
class AdminModelConnectionServiceTests {

    private static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final OffsetDateTime CREATED_AT =
            OffsetDateTime.of(2026, 11, 1, 9, 0, 0, 0, ZoneOffset.UTC);

    @Mock
    private AdminModelConnectionMapper adminModelConnectionMapper;

    @InjectMocks
    private AdminModelConnectionService adminModelConnectionService;

    @Test
    void listConnections_shouldMapCredentialMaskAndPushFiltersIntoQuery() {
        AdminModelConnectionQuery query = new AdminModelConnectionQuery();
        query.setUserId(USER_ID.toString());
        query.setProvider("openai");
        query.setStatus("ACTIVE");
        when(adminModelConnectionMapper.count(any())).thenReturn(1L);
        when(adminModelConnectionMapper.findPage(any(), anyLong(), anyInt()))
                .thenReturn(List.of(connectionRow()));

        var page = adminModelConnectionService.list(query);

        ArgumentCaptor<AdminConnectionFilter> filterCaptor =
                ArgumentCaptor.forClass(AdminConnectionFilter.class);
        verify(adminModelConnectionMapper).count(filterCaptor.capture());
        assertThat(filterCaptor.getValue().userId()).isEqualTo(USER_ID);
        assertThat(filterCaptor.getValue().provider()).isEqualTo("openai");
        assertThat(filterCaptor.getValue().status()).isEqualTo("ACTIVE");
        assertThat(page.total()).isEqualTo(1);
        assertThat(page.list()).singleElement().satisfies(item -> {
            assertThat(item.userId()).isEqualTo(USER_ID);
            assertThat(item.providerName()).isEqualTo("OpenAI");
            assertThat(item.credential()).isNotNull();
            assertThat(item.credential().maskedHint()).isEqualTo("sk-****abcd");
        });
    }

    @Test
    void listConnections_shouldReturnEmptyPage_whenNothingMatches() {
        AdminModelConnectionQuery query = new AdminModelConnectionQuery();
        when(adminModelConnectionMapper.count(any())).thenReturn(0L);

        var page = adminModelConnectionService.list(query);

        assertThat(page.list()).isEmpty();
        verify(adminModelConnectionMapper, never()).findPage(any(), anyLong(), anyInt());
    }

    @Test
    void listConnections_shouldRejectMalformedUserId() {
        AdminModelConnectionQuery query = new AdminModelConnectionQuery();
        query.setUserId("not-a-uuid");

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelConnectionService.list(query))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelConnectionMapper);
    }

    @Test
    void listConnections_shouldTreatBlankFiltersAsAbsent() {
        AdminModelConnectionQuery query = new AdminModelConnectionQuery();
        query.setProvider("  ");
        query.setStatus("");
        when(adminModelConnectionMapper.count(any())).thenReturn(1L);
        when(adminModelConnectionMapper.findPage(any(), anyLong(), anyInt()))
                .thenReturn(List.of(connectionRow()));

        var page = adminModelConnectionService.list(query);

        assertThat(page.list()).hasSize(1);
    }

    private static AdminConnectionRow connectionRow() {
        return new AdminConnectionRow(
                UUID.fromString("44444444-4444-4444-4444-444444444444"),
                USER_ID,
                "demo",
                "演示账号",
                "openai",
                "OpenAI",
                "https://api.openai.com/v1",
                "ACTIVE",
                CREATED_AT,
                CREATED_AT,
                UUID.fromString("55555555-5555-5555-5555-555555555555"),
                "sk-****abcd",
                "ACTIVE",
                CREATED_AT);
    }
}
