## Context

seek 已有 `doctor`，但它主要校验项目 SLS 配置与本地数据库连接，不负责首次接入时发现 A1、DMS MCP 和 SLS 凭据是否齐备。现有依赖说明散落在 README 与 TROUBLESHOOTING 中，且 A1 仍展示旧的 `--buc` 登录形式。DMS 文档需要企业权限，当前环境无法直接读取正文，因此只将用户提供的文档 URL 作为权威入口，不推测其页面内容。

## Goals / Non-Goals

**Goals:**
- 提供一个统一、机器可读且人可操作的初始化检查入口。
- 默认不联网；显式 `--verify` 后才验证 A1 登录态和 DMS MCP。
- 为缺失项给出最短配置路径和验证命令。
- 永不输出真实凭据。

**Non-Goals:**
- 不代替用户安装 A1 CLI、修改 IDE MCP 配置或申请权限。
- 不自动写入 AK/SK，也不通过命令行参数接收秘密。
- 不替代 `seek doctor` 对具体 SLS project/logstore 的完整检查。
- 不验证用户提供文档的内容或可访问权限。

## Decisions

### D1. 新增独立顶层 `seek init`

初始化属于所有排查链路的共同前置能力，不放入某一条业务链路。命令返回 `ready`、逐项 `integrations`、`next_actions` 和安全提示，便于 Agent 与人工调用。

### D2. 默认只做本地检查

默认检查 PATH、配置文件结构、SDK 和凭据是否可解析，不启动外部命令。`--verify` 才运行 `a1 auth whoami` 与 DMS `tools/list`，避免首次执行时因网络、下载或登录弹窗阻塞。

### D3. SLS 分为凭据检查和目标验证

初始化只确认 SDK 与 AK/SK 成对可用，不尝试猜测目标 project/logstore。具体 SLS 权限、地域和活性仍由 `seek doctor` 验证，并作为初始化结果中的下一步命令。

### D4. 配置说明以动作列表而非自动写入实现

DMS MCP 配置和 A1 登录可能涉及浏览器授权；SLS 密钥属于敏感信息。命令只返回文档入口和命令模板，避免自动执行授权或把密钥写入历史记录。

## Risks / Trade-offs

- [本地配置存在但凭据已过期] → `--verify` 检查 A1/DMS；SLS 明确提示继续运行 `seek doctor`。
- [企业文档暂时不可访问] → 输出稳定文档 URL，同时保留基于当前 CLI 契约的最小配置提示。
- [错误输出意外包含秘密] → 不回显配置内容，外部失败只返回截断后的类别化摘要。
