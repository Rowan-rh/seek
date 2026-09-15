# Proposal: add-perf-telemetry

## Why

chain 排查会话执行偏慢，优化方向（批量命令 / IO 并行 / 子 agent 并行）缺少数据依据。对 40 个历史 completed 会话（~/.seek/sessions，2026-09-03 分析）的聚合显示：

- 链路总时长中位数：default 8.1min、alert-ticket 12.5min、emergency-stuck-task 26.2min
- 最热单步：emergency-stuck-task s1「判定卡单业务类型」中位 13.5min（max 20.4min）、s3「按链路分支排查」中位 5.6min

但 session 只记录了每步 `completed_at` 时间戳，**step 端到端耗时无法拆分为「LLM 思考 / 集成 IO / CLI 进程开销」归因**——无法判断该优先做命令批量化（砍 LLM 轮次）还是 IO 并行。需要先落耗时观测，积累几个真实会话的数据后再决定并行化方案。

## What Changes

- **新增 `seek_cli/perf_log.py`**：复刻 error_log.py 模式（JSONL + 独立 fcntl 锁 + 脱敏），写 `~/.seek/logs/perf.jsonl`，提供 `log_perf()` 与 `perf_span()` 两个入口。
- **L1 命令级埋点**：`cli.py main()` 包裹 `func(args)` 计时，每次 CLI 调用记录 command/duration_ms/status——覆盖 agent 每次调 seek 的真实开销。
- **L2 集成 IO 埋点**：`sls_client.query_logs`（单 logstore SDK 调用，detail 带 endpoint/project/logstore/count/query 摘要）、`a1_client` subprocess、`dms_client` MCP 调用——区分「哪个环境/region 的目标慢」。
- **会话关联**：`log_perf` 自动附带环境变量 `SEEK_SESSION_ID`（若存在），L1 记录可精确归属到 chain step；SKILL.md 指引 agent 执行 step 查询时带上。
- **开关**：settings KEY_SCHEMA 新增 `options.perf_log`（默认开启，`as_bool` 归一化）。
- **故障隔离**：perf 写入失败静默吞掉，stdout 契约零变化。

## Capabilities

### New Capabilities
- `perf-telemetry`: CLI 命令级与集成 IO 级耗时记录规范——记录字段、开关语义、故障隔离与脱敏规则、会话关联方式。

### Modified Capabilities
（无——不新增命令、不改 stdout JSON 契约、不改既有命令行为）

## Impact

- **代码**：新增 `cli/seek_cli/perf_log.py`；修改 `cli/seek_cli/cli.py`（L1 埋点）、`cli/seek_cli/integrations/sls_client.py`、`cli/seek_cli/integrations/a1_client.py`、`cli/seek_cli/integrations/dms_client.py`（L2 埋点）、`cli/seek_cli/settings.py`（KEY_SCHEMA 加 `options.perf_log`）。
- **测试**：新增 `cli/tests/test_perf_log.py`（记录写入/开关/写失败不阻断/SEEK_SESSION_ID/脱敏/端到端一条命令）。
- **文档**：`cli/README.md`、`references/command-reference.md`、`SKILL.md`（agent 指引：执行 step 查询时前缀 `SEEK_SESSION_ID=<id>`）。
- **Out of scope**：`seek perf report` 聚合分析命令（数据积累后另立 change）；dingtalk/expert/roar HTTP 埋点（按需后续补）。
