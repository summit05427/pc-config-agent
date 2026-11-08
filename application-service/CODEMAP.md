# application-service 代码地图
用途：只做定位索引，不是规范；编码约束见 .trae/rules-on-demand/20-backend-java.md，接口契约见 docs/api-contract.md。

## 入口
| 用途 | 路径 |
| --- | --- |
| 启动类 | src/main/java/com/example/agent/AgentApplicationServiceApplication.java |
| 主配置与环境配置 | src/main/resources/application.yaml、application-local.yaml、application-dev.yaml、application-test.yaml、application-prod.yaml |
| 鉴权与授权装配 | src/main/java/com/example/agent/shared/config/SecurityConfig.java |
| 统一响应与异常处理 | src/main/java/com/example/agent/shared/api/ApiResponse.java、shared/web/GlobalExceptionHandler.java |
| 数据库迁移 | src/main/resources/db/migration |
| MyBatis 映射 | src/main/resources/mapper/identity、mapper/model |

## 目录职责
| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| identity/{domain,application,infrastructure,web} | 用户、登录、刷新会话、偏好、密码、审计 | 模型目录与用量业务 |
| model/{domain,application,infrastructure,web,config} | 模型目录、Provider 连接、凭证、用量、额度、内部接口 | 身份认证与用户档案 |
| shared/api、shared/error | 统一响应、分页、错误码与业务异常 | 业务流程 |
| shared/config | 安全、CORS、OpenAPI、MyBatis、生产配置守卫 | 控制器与领域规则 |
| shared/security | JWT 编解码、TokenUse 过滤、来源校验 | 用户业务数据 |
| shared/web | 全局异常处理、RequestId / 请求元数据过滤器、客户端 IP | 领域逻辑 |
| src/main/resources/db/migration | Flyway 版本化 SQL | Java 代码 |
| src/main/resources/mapper | identity/model 的 MyBatis XML | 接口定义 |

## 常见改动落点
| 需求 | 落点 |
| --- | --- |
| 新增一个 API 端点 | <模块>/web/XxxController.java、<模块>/web/dto/*.java、<模块>/application/XxxService.java，按需改 shared/config/SecurityConfig.java |
| 新增或修改数据库表 | src/main/resources/db/migration/V<n>__xxx.sql、<模块>/infrastructure/XxxMapper.java、resources/mapper/<模块>/XxxMapper.xml |
| 新增查询条件或分页 | <模块>/web/dto/XxxQuery.java、<模块>/application/XxxService.java、对应 Mapper XML |
| 新增业务错误码 | identity/domain/IdentityErrorCode.java 或 model/domain/ModelErrorCode.java、shared/error/BusinessException.java |
| 修改 Token 签发与校验 | identity/infrastructure/JwtTokenService.java、shared/security/JwtKeyLoader.java、TokenUseFilter.java |
| 新增 Agent 内部接口 | model/web/*InternalController.java、model/application/ServiceTokenService.java、UserTokenValidator.java |
| 修改配置项 | src/main/resources/application*.yaml、仓库根 .env.example |

## 测试
测试位于 src/test/java 下同名包结构，命令 Windows `cd application-service; .\mvnw.cmd -q verify`，Linux/macOS `cd application-service && ./mvnw -q verify`。
