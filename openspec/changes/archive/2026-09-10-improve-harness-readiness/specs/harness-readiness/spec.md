# Delta: harness-readiness

## Purpose

提供不依赖线上服务的 Harness 就绪检查和确定性黑盒评测入口，使环境、资源、版本与核心 Agent 协议问题能在提交前被结构化发现。

## ADDED Requirements

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
仓库 SHALL 提供无需线上凭据和网络访问的 Harness 评测脚本。脚本 MUST 使用临时 `SEEK_HOME`，执行 CLI 黑盒场景并输出 JSON 汇总；任一必选场景失败时 MUST 返回非零退出码。

#### Scenario: 离线评测通过
- **WHEN** 执行 `python3 harness/run_evals.py`
- **THEN** 脚本验证帮助无副作用、capabilities 可解析、首步输入门禁、未完成报告拒绝、版本一致性和外部内容安全契约
- **AND** 输出 `status=ok` 及各场景结果
- **AND** 不访问真实 `~/.seek` 或线上服务
