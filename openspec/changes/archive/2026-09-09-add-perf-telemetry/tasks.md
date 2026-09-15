# Tasks: add-perf-telemetry

## 1. 核心模块（cli/seek_cli/perf_log.py）

- [x] 1.1 新建 `perf_log.py`：`~/.seek/logs/perf.jsonl` + 独立 fcntl 锁（复刻 error_log 模式）
- [x] 1.2 `log_perf(command, span, duration_ms, status, detail)`：SEEK_SESSION_ID 附带、detail 敏感键打码、query/cmd 截断 200 字符、写盘异常全吞
- [x] 1.3 `perf_span(command, span, detail)` contextmanager：perf_counter 计时，异常路径记 status=error 且异常上抛
- [x] 1.4 `enabled()`：读 `options.perf_log`（默认 true，沿用 as_bool 归一化）

## 2. L1 命令级埋点（cli/seek_cli/cli.py）

- [x] 2.1 `main()` 包裹 `func(args)` 计时，finally 记录 `span=command`（成功失败都记，status 取返回 dict）

## 3. L2 集成 IO 埋点（integrations/）

- [x] 3.1 `sls_client.query_logs`：包 `client.get_logs(req)`，detail 记 endpoint/project/logstore/count/query 摘要（span=sls_query）
- [x] 3.2 `a1_client` subprocess 调用点：detail 记 a1 子命令摘要（span=a1_subprocess）
- [x] 3.3 `dms_client` MCP 调用：含 server 冷启动耗时（span=dms_call）

## 4. 配置开关（cli/seek_cli/settings.py）

- [x] 4.1 KEY_SCHEMA 新增 `options.perf_log`（help 说明与默认开启语义）

## 5. 测试（cli/tests/test_perf_log.py）

- [x] 5.1 记录字段齐全（timestamp/command/span/status/duration_ms）；开关 false 不写；写失败不抛异常
- [x] 5.2 SEEK_SESSION_ID 附带与缺省；detail 脱敏与截断；perf_span 异常路径
- [x] 5.3 端到端：subprocess 跑轻量命令后 perf.jsonl 出现 `span=command` 记录
- [x] 5.4 `python -m unittest discover cli/tests` 全绿（含 test_pipe_stability 回归）

## 6. 文档与验证

- [x] 6.1 `cli/README.md`、`references/command-reference.md`：perf.jsonl 字段、开关、归因公式说明
- [x] 6.2 `SKILL.md`：agent 指引——chain 会话内调用 seek 命令时前缀 `SEEK_SESSION_ID=<session_id>`
- [x] 6.3 真实验证：跑一次 chain 会话后，perf.jsonl 能拆出 s1 步骤的 command/IO 耗时构成
- [x] 6.4 `openspec validate add-perf-telemetry --strict` 通过
