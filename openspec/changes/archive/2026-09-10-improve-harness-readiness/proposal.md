# Proposal: improve-harness-readiness

## Why

seek 的链路约束、结构化输出和本地持久化已经适合 Agent 调用，但在受限 Harness 中仍存在用户 HOME 写入、Skill/CLI 版本漂移无法在提交前阻断、缺少离线就绪检查和 Agent 安全回归入口的问题。需要把这些隐含运行前提变成可配置、可检查、可自动回归的产品能力。

## What Changes

- 新增 `SEEK_HOME`：统一覆盖 seek 的配置、链路覆盖、session、错误日志、性能日志、旧版兼容配置和版本标记目录；未设置时保持 `~/.seek` 兼容行为。
- 调整 CLI 启动副作用：`--help` 和参数解析失败前不再写版本标记文件。
- 新增 `seek harness check` 离线就绪检查，结构化报告存储目录可写性、内置资源、链路/模板、Skill/CLI 版本一致性以及可选外部依赖状态，不发起网络请求。
- 新增仓库级 `harness/run_evals.py`，在临时 `SEEK_HOME` 中执行确定性黑盒场景，覆盖帮助命令无副作用、能力发现、首步输入门禁、未完成报告拒绝、版本一致性和外部内容安全契约。
- 将 PR 检查入口升级为隔离环境下的全量单测、Harness 离线评测、文档一致性与裸 `except` 检查。
- 在 Skill 中加入外部日志、工单、聊天和文档均为不可信数据的明确规则，禁止执行其中携带的指令。
- 修正 Skill 的 `cli_version_ref`，新增仓库级强制一致性测试；功能版本升级并补充 CHANGELOG。

## Capabilities

### New Capabilities

- `runtime-home-isolation`: seek 可变运行时状态的统一根目录覆盖、默认兼容行为与只读帮助命令无副作用契约。
- `harness-readiness`: 离线 Harness 就绪检查、结构化结果和仓库级确定性场景评测入口。
- `external-evidence-safety`: 外部取证内容的不可信数据边界与提示词注入防护契约。

### Modified Capabilities

- `skill-install-consistency`: 在现有运行时版本告警之外，增加仓库测试/PR 阶段的 Skill `cli_version_ref` 与 CLI 版本强一致门禁。

## Impact

- **代码**：新增 `seek_cli/paths.py`、`commands/harness.py`；调整所有 `~/.seek` 可变路径、CLI 启动顺序、parser 与 capabilities。
- **测试与工具**：新增 Harness readiness 单测及 `harness/run_evals.py`；升级 `cli/run_checks.sh`。
- **文档**：更新 `SKILL.md`、README、CLI README、命令参考和 CHANGELOG。
- **兼容性**：未设置 `SEEK_HOME` 时路径和现有 CLI JSON 响应保持不变；新增命令不改变已有命令参数。
- **Out of scope**：本轮不实现链路条件 DAG、outputs 强类型证据 schema、外部 HTTP 自动重试或线上模型评测服务；这些作为后续独立 change。
