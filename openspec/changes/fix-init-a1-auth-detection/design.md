## Context

`seek init` 的 A1 检测由 `cli/seek_cli/commands/init_cmd.py` 的 `_a1_status(verify)` 实现：
- 常量 `A1_CONFIG = ~/.config/a1/config.yaml`（第 14 行）；
- `configured = bool(executable and A1_CONFIG.exists())`（第 34 行）；
- 默认分支：探测文件不存在 → `needs_auth`（第 48-50 行）；存在 → `configured_unverified`（第 51-52 行）；
- `--verify` 分支：`a1 auth whoami` returncode==0 → `status=ready, verified=true`（第 65-66 行），否则 `needs_auth`（第 67-68 行）；两个分支都**不回写** `configured`。

实测证据（本机）：A1 已登录，`a1 auth whoami --format json` 返回 account=hrh02420307、name=黄若昊；真实凭据文件是 `~/.config/a1/auth.yaml`（存在，权限 0600），`config.yaml` 不存在。因此默认 `seek init` 报 A1 `needs_auth`、顶层 `ready=false`、"2/3 项就绪"，与事实相反。

对照 DMS：`_dms_status` 在启动命令不可用时 `configured=false`（第 119 行）、verify 失败时 `configured=false`（第 132 行）、成功时 `verified=true`（第 137 行）。DMS 的 `configured` 在 verify 路径被实测结果修正，A1 没有——这是两者行为不一致的根源。

## Goals / Non-Goals

**Goals:**
- 默认 `seek init` 对已登录 A1 不再误报 `needs_auth`；顶层 `ready` 能反映三项本地接入的真实就绪状态。
- `--verify` 下 A1 的 `configured` 与顶层 `ready` 由 `a1 auth whoami` 实测决定，使 spec「显式验证发现认证失败 → ready=false」在 A1 单独失败时也严格成立。
- A1 与 DMS 的 verify 回写语义对齐。

**Non-Goals:**
- 不改命令签名、参数、输出 JSON 结构或字段名。
- 不读取/解析 `auth.yaml` 内容，不新增外部调用。
- 不改 SLS 检测（SLS 活性仍由 `seek doctor` 负责，`--verify` 不实测 SLS 属既有设计）。
- 不自动执行 `a1 auth login` 或写入任何凭据。

## Decisions

### D1. 凭据探测路径改为 auth.yaml
将 `A1_CONFIG` 指向 `~/.config/a1/auth.yaml`。依据：本机实测 A1 登录凭据落盘于此（`config.yaml` 从未存在）。仅判断文件存在性，不读取内容，保持脱敏契约。

### D2. verify 模式以 whoami 实测覆盖 configured
`--verify` 成功（returncode==0）→ `configured=true, verified=true, status=ready`；认证失败（returncode!=0）→ `configured=false, status=needs_auth`；进程异常/超时 → `configured=false, status=verification_failed`。理由：登录态的权威判据是 `a1 auth whoami`，而非某个凭据文件是否落在固定路径。这样即便未来 A1 改用 keychain 或其他路径存凭据，verify 模式仍能正确判定；同时与 DMS 的 verify 回写行为一致。

### D3. 默认（不 verify）保持文件探测语义
默认不联网，`configured` 仍由「可执行文件 + auth.yaml 存在」判定，`status` 为 `configured_unverified`。这是 spec「默认只执行本地检查」的要求；登录态是否真有效留给 `--verify`。

### D4. 顶层 ready 计算不变
`ready = all(item["configured"])` 保持不变。修复后 A1 的 `configured` 语义正确，`ready` 自然恢复可信，无需改聚合逻辑。

## Risks / Trade-offs

- [A1 未来变更凭据文件名/位置] → D2 让 verify 模式以 whoami 为准，可容忍探测路径漂移；默认模式仍可能因文件探测失真，但默认本就不保证登录态有效。
- [auth.yaml 存在但登录已过期] → 默认报 `configured_unverified`（不谎称已验证）；`--verify` 通过 whoami 检出并置 `configured=false`、顶层 `ready=false`。
- [测试依赖宿主机 ~/.config/a1] → 用 `mock.patch.object(init_cmd, "A1_CONFIG", ...)` 指向临时路径隔离，避免开发机凭据存在与否影响断言。
