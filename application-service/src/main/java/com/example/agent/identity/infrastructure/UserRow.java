package com.example.agent.identity.infrastructure;

import java.time.Instant;
import lombok.Getter;
import lombok.Setter;

/**
 * {@code users} 表的行映射对象。
 *
 * <p>MyBatis 需要无参构造与 setter，因此不使用 record；
 * {@code roles} 在库里是逗号分隔文本，转换逻辑留在 {@link MyBatisUserDirectory}。</p>
 */
@Getter
@Setter
public class UserRow {

    private Long id;
    private String publicId;
    private String username;
    private String passwordHash;
    private String email;
    private String displayName;
    private String bio;
    private String roles;
    private String status;
    private Instant createdAt;
    private Instant updatedAt;
}
