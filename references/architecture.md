# 架构说明

seek 将“排查方法”和“数据源实现”分离：

```text
Agent
  ↓ 结构化命令 / Chain gate
seek core
  ├─ Chain：步骤与约束
  ├─ Session：状态与上下文
  ├─ Evidence：来源与边界
  ├─ Report：可复用输出
  └─ Plugin registry：发现 Provider
       ↓
  独立插件：日志、指标、部署、数据库、业务系统
```

核心不导入插件 SDK，也不解释 Provider 的内部配置。插件通过 `seek.plugins` entry point 注册，并自行负责凭据、连接、健康检查和命令实现。

## 设计原则

- 核心依赖稳定的数据契约，不依赖某个产品的 API 形态。
- 插件可以独立发布、升级和替换。
- 用户项目配置只描述项目身份和通用 metadata。
- Chain 文件可覆盖内置定义，用于组织团队自己的排查方法。
- 所有外部数据都需要来源和验证边界。
