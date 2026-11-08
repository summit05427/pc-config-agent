/**
 * PC 配置推荐模块：硬件目录、跑分、报价、兼容性校验、确定性求解与方案快照。
 *
 * <p>{@code domain} 存放纯领域对象与规则；{@code application} 编排查询、校验、求解与快照事务；
 * {@code infrastructure} 是 JSON fixture 与 MyBatis 适配器；{@code web} 只承载内部接口。
 * 上层不得直接读取 classpath 文件，也不得依赖其他业务模块的内部包。</p>
 */
@ApplicationModule
package com.example.agent.pcbuild;

import org.springframework.modulith.ApplicationModule;
