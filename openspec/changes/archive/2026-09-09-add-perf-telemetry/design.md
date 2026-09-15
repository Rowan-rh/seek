# Design: add-perf-telemetry

## D1. 记录 schema 与存储

文件：`~/.seek/logs/perf.jsonl`（每行一个 JSON，append-only），独立锁文件 `perf.lock`（与 errors.jsonl 模式一致，不共用锁）。

```json
{
  "timestamp": "2026-09-03T10:00:00.000000",
  "command": "sls query",
  "span": "command",          // command | sls_query | a1_subprocess | dms_call
  "status": "success",       // success | error
  "duration_ms": 1840,
  "session_id": "011d8679eec4",   // 可选，来自环境变量 SEEK_SESSION_ID
  "detail": {"project": "qt-stability", "env": "prod", "logstore": "xxx", "count": 57}
}
```

- `perf_span(command, span, detail)` 为 contextmanager：进入记 t0，退出写一条记录（异常时 status=error，异常仍正常上抛）；`log_perf(...)` 为裸函数入口。
- duration 用 `time.perf_counter()` 单调钟差值取整毫秒。

## D2. L1 命令级埋点（cli.py main()）

在 `result = func(args)` 外包裹计时（`cmd_name` 已有现成构造），finally 中记录——成功失败都记，`status` 取自返回 dict 的 `status` 字段。**计时区间只覆盖 func(args)，不含 argparse/print_result**。开关关闭时计时照常、只是不落盘（读开关在写盘时判断，读文件 ~1ms 不在计时区间内）。

## D3. L2 集成 IO 埋点

- `sls_client.query_logs`：包 `client.get_logs(req)`，detail 记 endpoint/project/logstore/count/query（截断 200 字符）。`query_by_config` 多 logstore 循环调用它，天然逐 logstore 出记录——「每个环境的 logstore 慢不慢」由这里回答。
- `a1_client`：包公共 subprocess 调用点，detail 记 a1 子命令摘要。
- `dms_client`：包 MCP query 调用（含 server 冷启动耗时，这正是历史 s1 步骤慢的怀疑点之一）。
- 索引探测 `get_index_summary`、dingtalk/expert/roar 暂不埋（out of scope）。

## D4. 开关与故障隔离

- `settings.KEY_SCHEMA` 新增 `options.perf_log`（help: 记录命令与集成耗时到 ~/.seek/logs/perf.jsonl），布尔归一化沿用 `as_bool`；`perf_log.enabled()` 读该键，**默认 true**（未设置即开）。
- `log_perf` 整体 try/except 吞掉一切写盘异常（含目录不可写）——观测绝不能阻断命令。
- stdout 恒为 `print_result` 输出，perf 日志只走文件，pipe stability 契约零变化。

## D5. 会话关联（step 归因）

`log_perf` 附带 `os.environ.get("SEEK_SESSION_ID")`（存在才写）。SKILL.md 增加 agent 指引：chain 会话内执行查询命令时用 `SEEK_SESSION_ID=<session_id> seek sls query ...` 前缀调用。归因公式：

```
step 端到端耗时（session completed_at 差）
  − 该时间窗内 span=command 的 duration_ms 总和      → LLM+编排开销
command duration 内再按 span=sls_query/a1_subprocess/dms_call 拆分 IO 构成
```

无 session_id 时按时间窗近似对齐（会话数量少、时间不重叠，近似足够）。

## D6. 脱敏

复用 error_log 的敏感键规则（ACCESS_KEY_ID/SECRET/PASSWORD/TOKEN 打码）；`detail.query`/`detail.cmd` 截断 200 字符；不记录凭据与完整 SQL 大字段。

## D7. 测试策略（test_perf_log.py）

- 临时目录替换 `perf_log._LOG_DIR/_LOG_FILE`（沿用 error_log 测试模式）。
- 用例：成功写入字段齐全；开关 false 不写；`_LOG_FILE` 指向不可写路径时 log_perf 不抛异常且命令返回不受影响；SEEK_SESSION_ID 附带与缺省；detail 敏感键打码与截断；perf_span 异常路径记 status=error 且异常上抛。
- 端到端：subprocess 跑 `seek version`（或轻量命令）后 perf.jsonl 出现 `span=command` 记录。
- 回归：`python -m unittest discover cli/tests` 全绿（重点 test_pipe_stability 确认 stdout 契约不受影响）。

## D8. 边界与兼容

- 不新增 CLI 命令，capabilities 契约不变（`options.perf_log` 属 config 命令组既有键值域的自然扩展）。
- `options.perf_log` 未设置时行为 = 开启（默认收集数据，用户可 `seek config set options.perf_log false` 关闭）。
- 旧版本写入的 session/perf 数据无迁移问题（增量文件）。
