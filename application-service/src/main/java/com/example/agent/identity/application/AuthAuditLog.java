package com.example.agent.identity.application;

/**
 * 认证审计写入端口。
 *
 * <p>应用层只依赖该接口，具体存储由基础设施层实现；测试用内存实现替换，
 * 因此审计写入不成为业务测试的数据库依赖。</p>
 */
public interface AuthAuditLog {

    /**
     * 追加一条审计记录。
     *
     * @param entry 待写入记录
     */
    void append(AuthAuditEntry entry);
}
