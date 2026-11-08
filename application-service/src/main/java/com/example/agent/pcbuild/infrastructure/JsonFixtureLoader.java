package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;
import tools.jackson.databind.ObjectMapper;

/**
 * classpath JSON fixture 加载器。
 *
 * <p>只在基础设施层使用：启动期一次性读入并缓存，上层服务与领域对象永远不会接触文件系统。
 * 加载失败直接阻止启动，避免运行期出现「空目录却返回空列表」的静默降级。</p>
 */
final class JsonFixtureLoader {

    private JsonFixtureLoader() {
    }

    /**
     * @param objectMapper Jackson 映射器
     * @param resourcePath classpath 路径
     * @param type         目标类型
     * @param <T>          目标类型
     * @return 反序列化结果
     * @throws IllegalStateException 资源缺失或格式非法
     */
    static <T> T load(ObjectMapper objectMapper, String resourcePath, Class<T> type) {
        ClassPathResource resource = new ClassPathResource(resourcePath);
        if (!resource.exists()) {
            throw new BusinessException(PcBuildErrorCode.CATALOG_UNAVAILABLE,
                    "硬件目录缺失: " + resourcePath);
        }
        try (InputStream inputStream = resource.getInputStream()) {
            return objectMapper.readValue(inputStream, type);
        } catch (IOException ex) {
            throw new IllegalStateException("无法解析 PC 配置 fixture: " + resourcePath, ex);
        }
    }
}
