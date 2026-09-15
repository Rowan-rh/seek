## Why

`seek init` 通过检查 `~/.config/a1/config.yaml` 是否存在来判断 A1 CLI 登录态，但 A1 CLI 实际把登录凭据写入 `~/.config/a1/auth.yaml`，`config.yaml` 从不存在。因此：

- 默认 `seek init` 恒将 A1 CLI 误报为 `needs_auth`「未发现默认登录配置」，即使用户已 `a1 auth login` 且 `a1 auth whoami` 能正常返回身份；
- A1 的 `configured` 字段恒为 `false`，导致顶层 `ready = all(configured)` 恒为 `false`，"N/3 项本地接入已就绪" 永远最多 2/3；
- `--verify` 分支即使 `a1 auth whoami` 成功、A1 `status` 已修正为 `ready`，也未回写 `configured`，顶层 `ready` 仍为 `false`。

这与 DMS MCP 的行为不一致：DMS 在启动命令不可用或 verify 失败时会把 `configured` 降级为 `false`，成功时置 `verified=true`，使顶层 `ready` 能反映实测结果。A1 缺少同样的回写，既造成误报，也让 spec「显式验证发现认证失败 → ready=false」在 A1 单独失败场景下依赖"碰巧"的 `configured=false`（一旦修正探测路径就会失效）。

## What Changes

- 修正 A1 登录凭据文件探测路径：`~/.config/a1/config.yaml` → `~/.config/a1/auth.yaml`，对齐 A1 CLI 真实凭据存储。
- `--verify` 模式下 A1 的 `configured` 由 `a1 auth whoami` 实测结果决定：成功回写 `configured=true`（即使凭据不在探测路径，如存于 keychain），失败或进程异常回写 `configured=false`，与 DMS MCP 行为对齐。
- 加固单元测试：隔离对宿主机 `~/.config/a1/` 的环境依赖，覆盖「默认已登录不误报 needs_auth」「verify 成功 configured=true」「verify 失败即使凭据文件存在也 configured=false 且 ready=false」。

## Capabilities

### Modified Capabilities
- `integration-initialization`: 修正 A1 CLI 登录凭据探测路径，并使 `--verify` 下 A1 的 `configured` 与顶层 `ready` 反映实测登录态。

## Impact

- **CLI**：`seek init` / `seek init --verify` 对 A1 CLI 的状态判定（`configured`/`status`/顶层 `ready`）。命令签名、参数与输出 JSON 结构不变。
- **集成**：仅本地文件探测路径与 verify 回写逻辑变化；不新增外部调用，`--verify` 仍只跑 `a1 auth whoami`。
- **安全**：不读取、不回显 `auth.yaml` 内容，仅判断文件是否存在；凭据脱敏契约不变。
- **版本**：patch 升级 0.10.0 → 0.10.1，同步 SKILL.md `cli_version_ref` 与 CHANGELOG。
