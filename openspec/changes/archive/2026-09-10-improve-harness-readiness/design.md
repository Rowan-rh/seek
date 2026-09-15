# Design: improve-harness-readiness

## Context

当前所有 seek 可变状态默认落在 `~/.seek`，各模块在导入时分别构造路径。链路和 CLI 契约已有较完整单测，但直接在受限 Harness 中运行时，未隔离的测试会尝试写真实 HOME；仓库也缺少一个无需线上凭据即可执行的黑盒评测入口。Skill 已能在运行时报告版本漂移，但提交前没有硬门禁，且未明确外部证据内容的提示词注入边界。

## Goals / Non-Goals

**Goals:**

- 用一个环境变量隔离全部 seek 自有可变状态；
- 提供结构化、离线、无网络的 Harness readiness 检查；
- 提供可在 PR 中执行的确定性 CLI 黑盒场景；
- 把版本一致性和外部内容信任边界变成可测试契约；
- 保持未设置新变量时的现有路径和已有命令响应兼容。

**Non-Goals:**

- 不在本轮实现线上 LLM judge 或调用真实 A1/SLS/DMS；
- 不实现链路条件 DAG、强类型 outputs schema 或自动重试；
- 不改变 Qoder/QoderWork Skill 安装目录；`SEEK_HOME` 仅控制 seek 自有状态；
- 不改变既有 success/error 顶层 JSON 结构。

## Decisions

### D1. 新增集中式 paths 模块

新增 `seek_cli.paths`，提供 `seek_home()` 和 `seek_path()`。`SEEK_HOME` 非空时优先，否则返回 `Path.home() / ".seek"`。各现有模块保留原路径常量名，以减少改动和保持测试 patch 兼容，但常量统一由 paths 模块初始化。

选择单根目录而不是本轮完整拆分 XDG config/state，是为了保持现有目录结构、文档和迁移成本稳定；后续可以在不改变 `SEEK_HOME` 契约的前提下扩展 XDG。

### D2. 帮助命令先解析、后做版本变更检查

把 `_check_version_change()` 从 parser 构建前移动到成功解析且确认存在命令处理函数之后。argparse 的 `--help` 会在解析阶段退出，因此不会创建版本文件。正常业务命令仍保持版本提示行为。

### D3. readiness check 分为 failure 与 warning

`seek harness check` 逐项执行检查并收集结果：

- failure：seek home 不可写、内置配置/链路/模板无效、源码树中版本明确漂移；
- warning：Skill 文件在已安装 wheel 中不可见、A1/dws 等可选外部命令缺失、当前 host 使用 HTTP；
- pass：检查满足。

命令不调用网络。存在 failure 时通过标准 `error(..., code="HARNESS_NOT_READY", data=report)` 返回；只有 warning 时仍为成功。

### D4. 黑盒评测使用 subprocess 和临时 SEEK_HOME

`harness/run_evals.py` 使用当前 Python 解释器启动 `python -m seek_cli`，通过环境变量指向临时目录，并为每个场景校验退出码、stdout JSON 和文件系统副作用。这样覆盖真实 parser、main、命令路由和持久化边界，而不是只调用内部函数。

脚本不依赖 pytest、coverage 或网络服务，确保开发机和 CI 都能直接运行。

### D5. 安全边界放在 Skill 硬约束并由静态评测守护

外部内容信任边界属于 Agent 行为契约，放在 `SKILL.md` 的硬约束中，而不是只写在参考文档。Harness 脚本和文档一致性测试检查关键语义仍存在，避免后续精简 Prompt 时误删。

### D6. PR 检查使用隔离状态目录

`cli/run_checks.sh` 创建临时目录并导出 `SEEK_HOME`，执行全量 unittest、Harness 黑盒评测和裸 except 检查。使用 trap 清理，避免污染开发者真实状态。

## Risks / Trade-offs

- **模块级路径常量仍在 import 时求值** → Harness 必须在进程启动前设置 `SEEK_HOME`；文档和评测脚本明确这一点，已有测试 patch 方式保持可用。
- **readiness 外部依赖检查不能证明凭据或服务可用** → 明确标记为 warning，并强调该命令不联网；线上可用性仍由 `seek doctor` 和具体命令验证。
- **Skill 文件在非 editable wheel 中可能不可见** → 版本检查返回 warning/unknown，不误判失败；源码仓库的 PR 测试负责强一致门禁。
- **全量测试增加 PR 执行时间** → 当前套件执行时间为秒级，可接受；后续增长后再按快慢分层。

## Migration Plan

1. 发布包含 `SEEK_HOME` 支持的新版本；未设置变量的用户无需迁移。
2. CI/Harness 在启动 CLI 前设置独立 `SEEK_HOME`。
3. 发布前运行 `bash cli/run_checks.sh` 和 `seek harness check`。
4. 若发生回退，删除环境变量即可恢复旧的 `~/.seek` 路径行为。
