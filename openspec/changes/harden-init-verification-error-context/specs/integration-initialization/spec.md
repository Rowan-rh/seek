## MODIFIED Requirements

### Requirement: 初始化命令必须检查必要集成
系统 SHALL 提供 `seek init` 命令，检查 A1 CLI 是否安装、DMS MCP 配置是否存在且结构有效、SLS SDK 与 AK/SK 是否已配置，并以结构化结果返回每项状态。输出 MUST 区分本地配置状态（`configured`）与在线验证状态（`verified`）；未执行的在线验证不得被表示为验证失败。

#### Scenario: 所有本地前置均已配置
- **WHEN** A1 CLI 可执行文件存在、DMS MCP 配置有效且启动命令可用、SLS SDK 与 AK/SK 均可解析
- **THEN** `seek init` 返回成功并标记 `ready=true`
- **AND** 每项集成包含独立的状态和验证命令
- **AND** 未请求在线验证的项目 `verified` 保持 false，但不因此把本地 `ready` 标记为 false

#### Scenario: 存在未配置依赖
- **WHEN** 任一必要集成缺失、配置损坏或凭据不完整
- **THEN** `seek init` 仍返回结构化初始化清单并标记 `ready=false`
- **AND** `next_actions` 仅列出需要用户处理的步骤

### Requirement: 初始化引导必须提供权威入口
系统 SHALL 为 DMS MCP 和 A1 CLI 返回对应配置文档地址，并为 SLS 返回 AK/SK 支持的配置方式及验证命令。

#### Scenario: DMS MCP 未配置
- **WHEN** `~/.qoderwork/mcp.json` 不存在或缺少 `dms-mcp-server`
- **THEN** 输出 DMS MCP 文档地址、目标配置路径和 `seek db tools` 验证命令

#### Scenario: A1 CLI 未安装或未登录
- **WHEN** 未找到 `a1` 可执行文件，或显式验证登录态失败
- **THEN** 输出 A1 CLI 文档地址、`a1 auth login` 配置命令和 `a1 auth whoami --format json` 验证命令

#### Scenario: SLS 凭据未配置
- **WHEN** 无法成对解析 AccessKey ID 与 AccessKey Secret
- **THEN** 输出环境变量与 `seek config set` 两种配置方式
- **AND** 提醒用户不得在对话、日志或代码仓库中粘贴真实密钥

### Requirement: 初始化输出不得泄露凭据
初始化命令 MUST NOT 返回 AK、SK、Token、MCP URL 查询参数或配置文件中的其他秘密值；错误详情也必须经过截断和凭据脱敏。

#### Scenario: 已配置敏感信息
- **WHEN** SLS 或 DMS 配置中包含真实凭据
- **THEN** 输出仅包含凭据是否存在及其来源类别
- **AND** 不包含原始凭据值

### Requirement: 外部验证必须显式启用
默认 `seek init` SHALL 只执行本地文件和可执行程序检查。仅当用户传入 `--verify` 时，系统 SHALL 尝试验证 A1 登录态和 DMS MCP 工具发现；验证失败 SHALL 转化为结构化状态和修复建议，不得导致未捕获异常。SLS 的 `seek init` 检查 SHALL 只判断 SDK 与凭据是否已配置；SLS 资源活性验证 SHALL 继续由 `seek doctor --liveness-window 24h` 执行，并在初始化输出中明确表示该边界。

#### Scenario: 默认初始化不访问外部服务
- **WHEN** 用户执行 `seek init`
- **THEN** 不调用 A1 或 DMS 外部进程进行认证/连通性验证
- **AND** `fully_ready` 不得因未执行 SLS doctor 而被标记为验证失败

#### Scenario: 显式验证发现认证失败
- **WHEN** 用户执行 `seek init --verify` 且 A1 或 DMS 验证失败
- **THEN** 对应集成标记为 `needs_auth` 或 `verification_failed`
- **AND** 总体 `ready=false` 并返回下一步命令

#### Scenario: 显式验证可验证集成全部成功
- **WHEN** 用户执行 `seek init --verify` 且 A1 与 DMS 在线验证成功、SLS SDK 与成对凭据已配置
- **THEN** `ready=true`
- **AND** `fully_ready=true` 表示所有由 `seek init --verify` 负责的检查均成功
- **AND** 输出明确说明 SLS 资源活性仍需通过 `seek doctor --liveness-window 24h` 验证
