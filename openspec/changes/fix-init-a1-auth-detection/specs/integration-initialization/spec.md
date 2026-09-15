## MODIFIED Requirements

### Requirement: 初始化命令必须检查必要集成
系统 SHALL 提供 `seek init` 命令，检查 A1 CLI 是否安装、DMS MCP 配置是否存在且结构有效、SLS SDK 与 AK/SK 是否已配置，并以结构化结果返回每项状态。A1 CLI 的本地就绪判定 SHALL 基于其真实登录凭据文件 `~/.config/a1/auth.yaml` 是否存在，而非其他路径。

#### Scenario: 所有本地前置均已配置
- **WHEN** A1 CLI 可执行文件存在且 `~/.config/a1/auth.yaml` 存在、DMS MCP 配置有效且启动命令可用、SLS SDK 与 AK/SK 均可解析
- **THEN** `seek init` 返回成功并标记 `ready=true`
- **AND** 每项集成包含独立的状态和验证命令

#### Scenario: A1 已登录不得误报缺配置
- **WHEN** A1 CLI 可执行文件存在且 `~/.config/a1/auth.yaml` 存在，但未传 `--verify`
- **THEN** A1 CLI 的 `configured=true` 且状态为 `configured_unverified`
- **AND** 不得标记为 `needs_auth`

#### Scenario: 存在未配置依赖
- **WHEN** 任一必要集成缺失、配置损坏或凭据不完整
- **THEN** `seek init` 仍返回结构化初始化清单并标记 `ready=false`
- **AND** `next_actions` 仅列出需要用户处理的步骤

### Requirement: 外部验证必须显式启用
默认 `seek init` SHALL 只执行本地文件和可执行程序检查。仅当用户传入 `--verify` 时，系统 SHALL 尝试验证 A1 登录态和 DMS MCP 工具发现；验证失败 SHALL 转化为结构化状态和修复建议，不得导致未捕获异常。`--verify` 模式下 A1 CLI 与 DMS MCP 的 `configured` 字段 SHALL 由实测结果决定：验证成功置为 `true`，验证失败置为 `false`，使顶层 `ready` 反映实测就绪状态。

#### Scenario: 默认初始化不访问外部服务
- **WHEN** 用户执行 `seek init`
- **THEN** 不调用 A1 或 DMS 外部进程进行认证/连通性验证

#### Scenario: 显式验证成功修正就绪状态
- **WHEN** 用户执行 `seek init --verify` 且 `a1 auth whoami` 返回成功
- **THEN** A1 CLI 标记为 `ready`、`verified=true` 且 `configured=true`
- **AND** 即使登录凭据不在探测路径（如存于系统 keychain），也以实测结果为准

#### Scenario: 显式验证发现认证失败
- **WHEN** 用户执行 `seek init --verify` 且 A1 或 DMS 验证失败
- **THEN** 对应集成标记为 `needs_auth` 或 `verification_failed` 且 `configured=false`
- **AND** 总体 `ready=false` 并返回下一步命令
