package com.example.agent.model.application;

import com.example.agent.shared.config.ModelRuntimeProperties;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * 模型凭证主密钥环。
 *
 * <p>密钥环属于模型凭证能力，格式与校验规则此前写在通用配置类里，且每次加解密都会
 * 重新切分、解码字符串。这里在启动时解析一次：配置了 {@code key-ring} 就只认它，
 * 任一项非法或缺少当前写入版本都直接让启动失败；未配置时退回单密钥，且只接受与
 * {@code key-version} 相同的密文版本。</p>
 */
@Component
public class CredentialKeyRing {

    private static final int AES_KEY_BYTES = 32;
    private static final String ENTRY_SEPARATOR = ":";
    private static final String LIST_SEPARATOR = ",";

    private final Map<Integer, String> keysByVersion;
    private final int currentVersion;

    public CredentialKeyRing(ModelRuntimeProperties properties) {
        ModelRuntimeProperties.Credential credential = properties.getCredential();
        this.currentVersion = credential.getKeyVersion();
        String keyRing = credential.getKeyRing();
        if (keyRing == null || keyRing.isBlank()) {
            this.keysByVersion = singleKey(credential.getMasterKey(), currentVersion);
        } else {
            this.keysByVersion = parseKeyRing(keyRing, currentVersion);
        }
    }

    /**
     * 取指定版本的主密钥。
     *
     * @param version 密文中记录的密钥版本
     * @return base64 主密钥；该版本未配置时为 {@code null}
     */
    public String keyForVersion(int version) {
        return keysByVersion.get(version);
    }

    /**
     * @return 当前新密文写入的密钥版本
     */
    public int currentVersion() {
        return currentVersion;
    }

    /**
     * @return 当前写入版本是否已配置可用主密钥
     */
    public boolean isCurrentVersionUsable() {
        return keysByVersion.containsKey(currentVersion);
    }

    /**
     * 单密钥模式：未配置密钥环时只允许使用与当前写入版本相同的密钥。
     * 非法单密钥不抛异常，与「配置缺失」一样表现为不可用，由启用 BYOK 时的启动校验拦截。
     */
    private static Map<Integer, String> singleKey(String masterKey, int currentVersion) {
        if (masterKey == null || masterKey.isBlank() || !isAesKey(masterKey.trim())) {
            return Map.of();
        }
        return Map.of(currentVersion, masterKey.trim());
    }

    /**
     * 解析 {@code <version>:<base64>} 列表；任一项非法或缺少当前写入版本都视为整体不可用。
     */
    private static Map<Integer, String> parseKeyRing(String keyRing, int currentVersion) {
        Map<Integer, String> parsed = new LinkedHashMap<>();
        for (String rawEntry : keyRing.split(LIST_SEPARATOR)) {
            String entry = rawEntry.trim();
            int separator = entry.indexOf(ENTRY_SEPARATOR);
            if (separator <= 0 || separator >= entry.length() - 1) {
                throw invalidKeyRing();
            }
            try {
                int version = Integer.parseInt(entry.substring(0, separator).trim());
                String key = entry.substring(separator + 1).trim();
                if (version < 1 || !isAesKey(key)) {
                    throw invalidKeyRing();
                }
                parsed.putIfAbsent(version, key);
            } catch (IllegalArgumentException ex) {
                throw invalidKeyRing();
            }
        }
        if (!parsed.containsKey(currentVersion)) {
            throw invalidKeyRing();
        }
        return Map.copyOf(parsed);
    }

    private static boolean isAesKey(String base64Key) {
        try {
            return Base64.getDecoder().decode(base64Key).length == AES_KEY_BYTES;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static IllegalStateException invalidKeyRing() {
        return new IllegalStateException(
                "app.model.credential.key-ring 每项必须是 <version>:<32 字节 base64>，且包含 key-version 对应的密钥");
    }
}
