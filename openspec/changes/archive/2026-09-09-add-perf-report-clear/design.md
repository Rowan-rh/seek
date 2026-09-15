# Design: add-perf-report-clear

## D1. 数据读取与过滤（perf_log.py）

- `read_perf_records(time_range: str = "24h", command: str = "", session: str = "") -> list`
  - 文件不存在返回 `[]`（诊断命令，不报错）。
  - 时间窗复用 `sls_client._parse_time_range`（支持 `24h`/`7d`、`from,to` 时间戳与人类可读区间，与 SLS `--time` 同一套语法；函数内惰性 import，避免 perf_log 模块级引入 SDK 依赖）。
  - `timestamp` 用 `datetime.fromisoformat` 解析后与窗口比较（写入侧即本地时间 ISO）；解析失败或 JSON 损坏的行跳过（与 error_log.read_errors 容错口径一致），损坏行数计入 `skipped` 返回给调用方供输出。
  - `command` 过滤为大小写不敏感子串匹配（作用于所有 span 的 `command` 字段——command 记录存命令名，IO 记录存动作描述如 `sls p/l`）；`session` 为 `session_id` 精确匹配。
  - 返回 `(records, skipped_count)`；records 保持文件顺序（旧→新）。
- `clear_perf_log() -> int`：锁内统计行数 → mkstemp 空文件 → `os.replace`，复刻 `error_log.clear_errors`。

## D2. 聚合口径（commands/perf.py）

- 分组维度：
  - **commands**（span=command）：按 `command` 名分组。
  - **ioSpans**（span≠command）：按 `(span, command)` 分组——IO 记录的 `command` 字段是动作描述（如 `dms executeScript`、`sls qt-monitor-ops/prod`），组合键才能区分「哪个集成、哪个目标」。
- 每组指标：`count`、`errors`（status=error 计数）、`totalMs`、`avgMs`、`p50Ms`、`p95Ms`、`maxMs`。分位数用 nearest-rank（排序后取 `ceil(p*n)-1` 下标），样本少时退化为 max，不引入插值假设。
- 排序：两组均按 `totalMs` 降序——「先看最热的命令/目标」。
- **ioSharePct** = `Σ(io duration) / Σ(command duration) × 100`（四舍五入整数）。语义边界 MUST 在输出中说明：IO span 嵌套在 command 区间内，占比是**粗略近似**（多 logstore 串行时近似精确；并行 IO 时会低估、嵌套 command 重叠时可能高估）。归因只用于方向判断，不做精确分摊。

## D3. 输出结构与 hint 规则

```json
{
  "window": {"from": 1757..., "to": 1757..., "human": "24h"},
  "filters": {"command": null, "session": null},
  "totalRecords": 87, "skippedCorrupt": 0,
  "totals": {"commandCount": 30, "commandMs": 61200, "ioCount": 57,
              "ioMs": 44800, "ioSharePct": 73,
              "errorCommands": 2, "errorIoCalls": 0},
  "commands": [...], "ioSpans": [...],
  "sessions": [{"session_id": "011d86", "commandCount": 9,
                 "commandMs": 21000, "ioMs": 15500}],
  "hint": "..."
}
```

- `sessions` 仅在窗口内存在带 `session_id` 的记录时输出，按 commandMs 降序，用于把归因落到具体 chain 会话。
- hint 规则（message 末尾亦带同文摘要）：
  - 无 command 记录 → 提示窗口内无数据（检查 `options.perf_log` 是否开启、窗口是否过窄）。
  - ioSharePct ≥ 60 → 集成 IO 占比高，优先考虑 IO 并行 / DMS MCP server 常驻复用。
  - ioSharePct ≤ 25 → IO 占比低，耗时主要在 LLM/编排轮次，优先命令批量化。
  - 其余 → IO 与编排开销均衡，结合 p95 最热命令判断。
  - 恒带一句占比近似语义的边界说明。
- 成功路径恒 `status=ok`（诊断命令，空数据不是错误）。

## D4. 命令注册与契约

- `cli.py`：`perf` 命令组，子命令 `report`（`--time` 默认 24h / `--keyword` / `--session`）与 `clear`（无参数）。
- `capabilities.py` 同步登记（`test_capabilities_contract` 强制参数集与 parser 严格相等）。
- report 命令自身的 command 记录由 `main()` 在 `func` 返回后的 finally 写入，读取发生在 func 内，**不会自我计入**。
- 版本 0.4.4 + CHANGELOG 条目。

## D5. 测试策略（test_perf_report.py）

- 临时目录替换 `perf_log._LOG_DIR/_LOG_FILE`（沿用 test_perf_log 模式），构造合成记录：
  - 聚合正确性：多命令/多 span 的 count、errors、totalMs、p50/p95/max、ioSharePct 逐项断言。
  - 窗口过滤：窗口外旧记录被排除（构造历史 timestamp）。
  - `--session` / `--keyword` 过滤命中与空结果。
  - 容错：损坏 JSON 行被跳过且 skippedCorrupt 计数正确。
  - clear：清空返回条数、文件变空、文件不存在时返回 0。
  - 空数据：report 对缺失文件返回 ok + totalRecords 0 + 无数据 hint。
- 回归：`python -m unittest discover cli/tests` 全绿（含 capabilities 契约测试）。

## D6. 边界与兼容

- 不做自动轮转/滚动（out of scope，clear 提供手动管理）。
- 读取为全文件流式扫描：当前量级（单机会话日志）与 error_log 同权衡，可接受。
- 旧版本写入的记录无 schema 迁移问题（字段超集兼容：缺 detail/session_id 均不影响聚合）。
