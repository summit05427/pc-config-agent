/**
 * 身份模块：负责登录认证、当前登录用户查询与访问令牌签发。
 *
 * <p>{@code web} 是对外 HTTP 边界，{@code application} 承载用例编排，
 * {@code infrastructure} 存放内存引导账号与 JWT 签发等技术适配实现。
 * 技术共享代码位于同级的 {@code shared} 包，不属于任何业务模块。</p>
 */
@ApplicationModule
package com.example.agent.identity;

import org.springframework.modulith.ApplicationModule;
