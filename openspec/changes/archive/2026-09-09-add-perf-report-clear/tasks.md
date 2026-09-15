# Tasks: add-perf-report-clear

## 1. 引擎层（cli/seek_cli/perf_log.py）

- [x] 1.1 `read_perf_records(time_range, command, session)`：流式读取 + 窗口过滤（复用 `_parse_time_range`，惰性 import），损坏行跳过并计数，返回 `(records, skipped)`
- [x] 1.2 `clear_perf_log()`：锁内行数统计 → mkstemp 空文件 → `os.replace`，返回清除条数（复刻 error_log.clear_errors）

## 2. 命令层（cli/seek_cli/commands/perf.py + cli.py）

- [x] 2.1 `cmd_perf_report(args)`：按 D2/D3 聚合（commands/ioSpans 分组、nearest-rank 分位、ioSharePct、sessions 分组、hint 规则）
- [x] 2.2 `cmd_perf_clear(args)`：调用 clear_perf_log 并输出
- [x] 2.3 `cli.py` 注册 `perf` 命令组：`report --time/--keyword/--session`、`clear`
- [x] 2.4 `capabilities.py` 登记 perf 命令组（与 parser 参数集严格一致）

## 3. 文档与版本

- [x] 3.1 `cli/README.md`：perf 节补 report/clear 用法与输出结构说明
- [x] 3.2 `references/command-reference.md`、`SKILL.md` 耗时日志节同步
- [x] 3.3 `__init__.py`：版本 0.4.4 + CHANGELOG 条目

## 4. 测试（cli/tests/test_perf_report.py）

- [x] 4.1 聚合正确性：count/errors/totalMs/p50/p95/max/ioSharePct 逐项断言
- [x] 4.2 窗口过滤（窗口外记录排除）与 `--session`/`--keyword` 过滤
- [x] 4.3 容错：损坏行跳过 + skippedCorrupt 计数；空/缺失文件返回 ok 与无数据 hint
- [x] 4.4 clear：返回条数、文件清空、缺失文件返回 0

## 5. 验证

- [x] 5.1 `python3 -m seek_cli version` 启动正常
- [x] 5.2 `python3 -m unittest discover cli/tests` 全绿（含 capabilities 契约测试）
- [x] 5.3 真实数据冒烟：对本机 perf.jsonl 跑一次 report，输出结构符合 D3
