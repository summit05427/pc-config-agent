/**
 * 反馈模块：消息级赞踩的采集、查询、统计与导出。
 *
 * <p>{@code domain} 只放枚举与校验规则；{@code application} 负责归属校验与查询编排；
 * {@code infrastructure} 是 MyBatis 适配器；{@code web} 分用户侧与管理端两组接口。
 * 本模块不依赖其他业务模块，管理端列表的用户名通过 SQL 联表获取。</p>
 */
@ApplicationModule
package com.example.agent.feedback;

import org.springframework.modulith.ApplicationModule;
