# Delta: perf-report

## Purpose

定义 perf.jsonl 的聚合分析与清理规范：`seek perf report` 的读取过滤口径、聚合指标定义与归因占比语义，`seek perf clear` 的清理行为，使耗时观测数据可被 agent 与人直接消费，回答「优先做 IO 并行还是命令批量化」的方向问题。

## ADDED Requirements

### Requirement: 耗时聚合报告
`seek perf report` SHALL 按时间窗聚合 perf.jsonl 记录并输出：命令级分组（span=command，按 command 名）与 IO 级分组（span≠command，按 span+command 组合键）的 count/errors/totalMs/avgMs/p50Ms/p95Ms/maxMs，两组均按 totalMs 降序。时间窗语法 SHALL 与 SLS `--time` 一致（简写/from,to/人类可读区间），默认 24h。

#### Scenario: 命令与 IO 分组聚合
- **WHEN** 窗口内有 2 条 `sls query` command 记录与 3 条 sls_query IO 记录
- **THEN** commands 含 `sls query` 分组（count=2），ioSpans 含对应 sls_query 分组（count=3），指标按定义计算

#### Scenario: 窗口外记录排除
- **WHEN** 记录 timestamp 早于窗口下界
- **THEN** 该记录不计入任何聚合指标

### Requirement: 归因占比与优化方向提示
报告 SHALL 输出 `totals.ioSharePct`（ΣIO duration / Σcommand duration）与 sessions 分组（存在 session_id 记录时），并按规则输出 hint：占比 ≥60 提示优先 IO 并行/常驻复用；≤25 提示优先命令批量化；其余提示均衡并结合最热命令判断。输出 MUST 说明该占比为嵌套区间的粗略近似，仅用于方向判断。

#### Scenario: IO 占比高
- **WHEN** ΣioMs/ΣcommandMs = 73%
- **THEN** ioSharePct=73，hint 含 IO 并行方向建议与近似语义说明

#### Scenario: 窗口内无数据
- **WHEN** 窗口内无 command 记录
- **THEN** 返回 status=ok、totalRecords 表征无数据，hint 提示检查开关与窗口（空数据不是错误）

### Requirement: 过滤参数
report SHALL 支持 `--session`（session_id 精确匹配）与 `--keyword`（对记录 command 字段的大小写不敏感子串匹配）过滤；过滤条件 MUST 回显在输出的 filters 字段。

#### Scenario: 会话过滤
- **WHEN** `seek perf report --session 011d86`
- **THEN** 仅聚合 session_id=011d86 的记录，filters.session 回显该值

### Requirement: 损坏行容错
读取 SHALL 跳过无法解析的 JSON 行或 timestamp 字段，损坏行数 MUST 以 skippedCorrupt 字段输出，不得使命令失败。

#### Scenario: 混入损坏行
- **WHEN** perf.jsonl 含一行非法 JSON
- **THEN** 其余记录正常聚合，skippedCorrupt=1，命令返回 ok

### Requirement: 日志清理
`seek perf clear` SHALL 在文件锁内清空 perf.jsonl（原子替换），返回清除的记录条数；文件不存在时返回 0 且不报错。

#### Scenario: 清空后再报告
- **WHEN** `seek perf clear` 后立即 `seek perf report`
- **THEN** clear 返回先前条数，report 显示 totalRecords=0 与无数据 hint

### Requirement: 输出契约
report/clear SHALL 遵循既有 stdout JSON 契约（status/data/message），成功路径恒 ok；不修改 perf-telemetry 写入侧行为。report 命令自身产生的 command 记录写入发生在数据读取之后，MUST NOT 计入本次报告。

#### Scenario: report 不自我计入
- **WHEN** 执行 `seek perf report`
- **THEN** 输出的 totalRecords 不含本次 report 命令自身的记录
