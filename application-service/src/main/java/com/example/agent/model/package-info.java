/**
 * 模型运行时模块：模型目录、运行时任务授权、每日请求额度与使用明细。
 *
 * <p>{@code web} 同时承载对前端的公开接口与仅供 Agent 调用的内部接口；
 * {@code application} 负责编排与事务边界；{@code infrastructure} 是 MyBatis 数据访问；
 * {@code domain} 存放不影响传输结构的领域对象。</p>
 */
@ApplicationModule
package com.example.agent.model;

import org.springframework.modulith.ApplicationModule;
