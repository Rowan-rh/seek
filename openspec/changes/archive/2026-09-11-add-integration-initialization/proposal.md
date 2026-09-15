## Why

首次使用 seek 时，A1 CLI、DMS MCP 和 SLS 凭据分散在不同文档和配置入口，用户往往直到执行具体排查命令才发现依赖缺失。需要一个统一、无泄密的初始化入口，先检测本地接入状态，再给出对应文档、配置和验证动作。

## What Changes

- 新增顶层命令 `seek init`，检查 A1 CLI、DMS MCP 和 SLS 的本地安装/配置状态。
- 新增 `seek init --verify`，在用户显式要求时执行 A1 登录态和 DMS MCP 可用性验证；SLS 提供凭据检查并引导用 `seek doctor` 验证具体日志库。
- 输出每项能力的状态、用途、配置文档、配置步骤、验证命令和后续动作，且不回显 AK/SK、Token 或 MCP 密钥。
- 将初始化加入 `/seek` 的前置流程和 README，并更新 A1 登录命令为当前 CLI 推荐的 `a1 auth login`。
- 增加能力声明、单元测试、Harness 检查和版本记录。

## Capabilities

### New Capabilities
- `integration-initialization`: 定义外部依赖接入状态检查、配置引导、可选连通性验证和敏感信息保护。

### Modified Capabilities
- `harness-readiness`: 离线 Harness 应验证初始化命令在缺少外部配置时仍能稳定返回结构化引导。

## Impact

- **CLI**：新增 `seek init [--verify]` 顶层命令和命令实现模块。
- **集成**：只读检查本地 A1、DMS MCP、SLS 配置；仅 `--verify` 触发 A1/DMS 外部验证。
- **文档**：更新 README、CLI 文档、SKILL 和排查 SOP，加入用户提供的 DMS MCP/A1 CLI 文档入口。
- **安全**：所有输出只显示配置来源和状态，不输出任何凭据值。
