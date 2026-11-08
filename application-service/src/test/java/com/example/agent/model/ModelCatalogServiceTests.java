package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.infrastructure.ModelCatalogMapper;
import com.example.agent.model.infrastructure.ModelCatalogStore;
import com.example.agent.model.infrastructure.ModelRow;
import com.example.agent.model.infrastructure.ProviderCatalogStore;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

/**
 * 模型目录服务单测：分页边界与运行时开关都不启容器。
 *
 * <p>能力元数据用真实 Jackson 解析，验证的是「JSONB 文本能转成列表」而不是对
 * mapper 调用次数的断言。</p>
 */
@ExtendWith(MockitoExtension.class)
class ModelCatalogServiceTests {

    private static final UUID USER_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Mock
    private ModelCatalogMapper modelCatalogMapper;

    private ModelRuntimeProperties properties;

    private ModelCatalogService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new ModelCatalogService(
                new ModelCatalogStore(modelCatalogMapper), new ProviderCatalogStore(modelCatalogMapper),
                properties, new ModelRuntimeGuard(properties), JsonMapper.builder().build());
    }

    @Test
    void listAvailablePage_shouldReturnRequestedSliceAndTotal() {
        when(modelCatalogMapper.countVisible(USER_ID)).thenReturn(3L);
        when(modelCatalogMapper.findVisiblePage(USER_ID, 0L, 2)).thenReturn(List.of(
                row("openai", "gpt-4o-mini", "[\"text\"]", 128000),
                row("openai", "gpt-4o", "[\"text\",\"vision\"]", 200000)));
        PageQuery query = query(1, 2);

        PageResult<ResolvedModel> page = service.listAvailable(query, USER_ID);

        assertThat(page.total()).isEqualTo(3);
        assertThat(page.page()).isEqualTo(1);
        assertThat(page.size()).isEqualTo(2);
        assertThat(page.list()).extracting(ResolvedModel::reference)
                .containsExactly("openai:gpt-4o-mini", "openai:gpt-4o");
        assertThat(page.list().get(1).capabilities()).containsExactly("text", "vision");
    }

    @Test
    void listAvailablePage_shouldReturnEmptyPage_whenOffsetBeyondTotal() {
        when(modelCatalogMapper.countVisible(USER_ID)).thenReturn(2L);
        PageQuery query = query(2, 2);

        PageResult<ResolvedModel> page = service.listAvailable(query, USER_ID);

        assertThat(page.list()).isEmpty();
        assertThat(page.total()).isEqualTo(2);
        verify(modelCatalogMapper, never()).findVisiblePage(USER_ID, 2L, 2);
    }

    @Test
    void listAvailablePage_shouldReturnRuntimeDisabled_whenSwitchIsOff() {
        properties.setRuntimeEnabled(false);

        assertThatThrownBy(() -> service.listAvailable(query(1, 20), USER_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.RUNTIME_DISABLED));
        verifyNoInteractions(modelCatalogMapper);
    }

    @Test
    void findCapabilities_shouldReturnCatalogFlags() {
        when(modelCatalogMapper.findEnabledByKey("deepseek", "deepseek-v4-pro"))
                .thenReturn(row("deepseek", "deepseek-v4-pro",
                        "[\"text\",\"reasoning\",\"reasoning_visible\"]", null));

        assertThat(service.findCapabilities("deepseek:deepseek-v4-pro"))
                .containsExactly("text", "reasoning", "reasoning_visible");
    }

    @Test
    void findCapabilities_shouldReturnEmpty_whenModelIsNotEnabled() {
        // 任务仍在 TTL 内但目录已下架：读取能力位不能因此抛业务异常
        when(modelCatalogMapper.findEnabledByKey("openai", "gpt-4o")).thenReturn(null);

        assertThat(service.findCapabilities("openai:gpt-4o")).isEmpty();
    }

    private static PageQuery query(int page, int size) {
        PageQuery query = new PageQuery();
        query.setPage(page);
        query.setSize(size);
        return query;
    }

    private static ModelRow row(String providerCode, String modelKey, String capabilitiesJson, Integer contextWindow) {
        return new ModelRow(providerCode, modelKey, modelKey, contextWindow, capabilitiesJson);
    }
}
