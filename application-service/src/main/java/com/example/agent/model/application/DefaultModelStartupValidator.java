package com.example.agent.model.application;

import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * 启动期校验模型运行时的配置与平台默认模型。
 *
 * <p>默认模型参与每次 Auto 解析，一旦指向目录里不存在或已下架的引用，
 * 问题只会在运行期以 403 暴露。该错误依赖数据库内容，无法在绑定阶段发现，
 * 因此放在 Flyway 之后的启动钩子里 fail-fast，而不是等到用户第一次对话。</p>
 *
 * <p>启用 BYOK 时还要求当前写入版本已有可用主密钥：这类缺失在运行期只会表现为
 * 「录入成功但无法使用」，必须在启动阶段拒绝。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class DefaultModelStartupValidator implements ApplicationRunner {

    private final ModelRuntimeProperties properties;
    private final CredentialKeyRing credentialKeyRing;
    private final ModelCatalogService modelCatalogService;

    @Override
    public void run(ApplicationArguments args) {
        if (properties.isByokEnabled() && !credentialKeyRing.isCurrentVersionUsable()) {
            throw new IllegalStateException(
                    "启用 app.model.byok-enabled 时必须配置 32 字节 base64 的 master-key，"
                            + "或包含 key-version 对应条目的 key-ring");
        }
        if (!properties.isRuntimeEnabled()) {
            return;
        }
        String reference = properties.getDefaultModelKey();
        try {
            ResolvedModel resolved = modelCatalogService.requireAvailable(reference);
            log.info("默认模型校验通过 reference={} displayName={}", resolved.reference(), resolved.displayName());
        } catch (BusinessException error) {
            throw new IllegalStateException(
                    "app.model.default-model-key 在模型目录中不可用：" + reference + "，请检查种子数据或配置", error);
        }
    }
}
