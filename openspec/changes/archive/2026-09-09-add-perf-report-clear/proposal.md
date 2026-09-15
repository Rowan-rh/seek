# Proposal: add-perf-report-clear

## Why

perf 耗时观测（OpenSpec: add-perf-telemetry，v0.4.3 合入）已开始向 `~/.seek/logs/perf.jsonl` 积累数据，但该 change 明确将聚合分析列为 out of scope（"数据积累后另立 change"）。当前缺口：

- **数据不可消费**：perf.jsonl 只能手工 `jq`/肉眼分析，agent 与人都无法直接回答立项动机——"优先做 IO 并行还是命令批量化"。
- **无清理能力**：perf.jsonl 默认开启 + append-only，每次 CLI 调用至少一条记录，没有任何管理命令；errors.jsonl 有 `seek errors clear`，perf.jsonl 没有对称能力（2026-09-09 整体 CR 报告 P3 亦指出）。

## What Changes

- **新增 `seek perf report`**：按时间窗（默认 24h，复用 SLS `--time` 语法）聚合 perf.jsonl——命令级（span=command）与 IO 级（sls_query/a1_subprocess/dms_call）的 count/误差数/p50/p95/max，IO 耗时占命令耗时比例（ioSharePct）及优化方向 hint；支持 `--session`（会话归属过滤）与 `--keyword`（子串过滤）。
- **新增 `seek perf clear`**：清空 perf.jsonl（原子替换，返回清除条数），与 `seek errors clear` 对称。
- **引擎层扩展 `perf_log.py`**：`read_perf_records()`（流式读取 + 窗口过滤，损坏行跳过）与 `clear_perf_log()`（复用 error_log 的锁 + 原子替换模式）。
- 输出遵循既有 stdout JSON 契约；report 命令自身产生的 command 记录发生在读取之后，不会计入本次报告。

## Capabilities

### New Capabilities
- `perf-report`: perf.jsonl 的聚合分析与清理规范——读取过滤口径、聚合指标定义、归因占比语义、输出结构与 hint 规则。

### Modified Capabilities
（无——perf-telemetry 写入侧零改动；不修改既有命令行为）

## Impact

- **代码**：修改 `cli/seek_cli/perf_log.py`（读/清理）、`cli/seek_cli/cli.py`（注册 perf 命令组）；新增 `cli/seek_cli/commands/perf.py`；`cli/seek_cli/commands/capabilities.py` 同步登记。
- **测试**：新增 `cli/tests/test_perf_report.py`（聚合口径/窗口与会话过滤/损坏行容错/clear/空文件）。
- **文档**：`cli/README.md`、`references/command-reference.md`、`SKILL.md`（耗时日志节补 report/clear 用法）；CHANGELOG + 版本号 0.4.4。
- **Out of scope**：perf.jsonl 大小自动轮转（clear 已提供手动管理，自动滚动另立 change）；跨文件聚合（perf.jsonl 仅单机单文件）；doctor 集成体检纳入 perf 状态。
