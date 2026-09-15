# harness-readiness Specification

## Purpose
提供不依赖线上服务的 Harness 就绪检查和确定性黑盒评测入口，使环境、资源、版本与核心 Agent 协议问题能在提交前被结构化发现。

## Requirements

### Requirement: 离线 Harness 就绪检查
系统 SHALL 提供 `seek harness check` 命令，在不发起网络请求的前提下检查 seek home 可写性、内置项目配置、链路定义、报告模板、Skill/CLI 版本一致性和外部命令可用性，并返回统一 JSON 响应。

#### Scenario: 核心检查全部通过
- **WHEN** seek home 可写、内置资源有效且 Skill/CLI 版本一致
- **THEN** 返回 `status=ok`
- **AND** `data.ready=true`
- **AND** 每个检查项包含稳定的 `name`、`status` 和 `message`

#### Scenario: 核心检查失败
- **WHEN** seek home 不可写、内置资源损坏或版本明确不一致
- **THEN** 返回 `status=error`、错误码 `HARNESS_NOT_READY`
- **AND** `data.ready=false`
- **AND** 输出保留所有已完成检查项，不因单项失败丢失其余结果

#### Scenario: 可选外部命令缺失
- **WHEN** A1 或 dws 等外部命令不在 PATH
- **THEN** 对应检查项标记为 `warning`
- **AND** 不单独导致 `data.ready=false`

### Requirement: 确定性 Harness 回归入口
仓库 SHALL 提供无需线上凭据和网络访问的 Harness 评测脚本。脚本 MUST 使用临时 `SEEK_HOME`，执行 CLI 黑盒场景、初始化引导检查和内置 Agent 场景 replay，并输出 JSON 汇总；任一必选场景失败时 MUST 返回非零退出码。

#### Scenario: 离线评测通过
- **WHEN** 执行 `bash cli/run_checks.sh`
- **THEN** 脚本验证 CLI 黑盒契约、初始化引导并执行内置 Agent 场景 replay
- **AND** Agent 场景报告包含 protocol、trajectory、report 三层结果和聚合指标
- **AND** 全过程不访问真实 `~/.seek`、线上服务或真实 Agent

#### Scenario: 初始化引导离线检查
- **WHEN** Harness 在隔离 HOME、无 A1/DMS/SLS 配置的环境执行 `seek init`
- **THEN** 命令返回成功的结构化引导并标记 `ready=false`
- **AND** 返回 A1 CLI 与 DMS MCP 文档入口以及 SLS AK/SK 配置动作
- **AND** 不访问外部服务或输出任何真实凭据

#### Scenario: 不可写 seek home 返回结构化错误
- **WHEN** 黑盒场景将 `SEEK_HOME` 指向无法作为目录写入的路径并执行 `seek harness check`
- **THEN** stdout 仍为可解析 JSON
- **AND** 返回 `status=error`、错误码 `HARNESS_NOT_READY`
- **AND** stderr 包含版本标记和错误日志写入失败的降级提示
