# Design: add-emergency-case-patterns

## Context

- 6 例排查报告与汇总文档已存在于 `stability-locate/doc/`（工作区外），本变更只把其中"按指纹可命中"的故障模式与可复用方法论搬入本仓库知识页。
- 既有案例库 `references/emergency-response-patterns.md` 的「已知故障模式快速匹配」表已有 CASE-001 ~ CASE-010，行格式为「案例 | 故障指纹 | 核心结论」。
- `references/evidence-and-boundaries.md` 已有通用规则覆盖：关键词静默返 0（分词/无索引）、文档记载数据源 ≠ 活数据源、trace 缺失替代证据。

## Decisions

### D1：编号续接为 CASE-011 / 012 / 013

- 入库前实测现有最大编号为 CASE-010（配置缓存与 force push merge 已占用 CASE-009/010）。
- alert 报告自提的"CASE-009 候选"与既有编号冲突，按 spec 规则顺延，不沿用。

### D2：三条新模式入「已知故障模式快速匹配」表，详情条目放案例小节

- 表格行保持既有三列格式（案例 | 故障指纹 | 核心结论），保证指纹速查体验不变。
- 四要素详情（指纹/根因/处置/检索入口）以紧凑小节形式放在该表之后新增的「新增案例详情（2026-08）」小节，避免把表格撑爆。

### D3：CASE-004 成因变体、CASE-003 占用方更正用"行内追加"而非改行

- CASE-003 行核心结论追加一句占用方发起方式提示；CASE-004 行追加成因变体提示。原结论文本保留，符合"更正以追加方式进行"。

### D4：方法论沉淀为应急页独立小节，通用陷阱只补具体实例

- 「案例排查方法论」小节收纳：四步定位归属法、requestId 串联三日志、下游错误三分法、`aliyunpop dx` 深挖。这些是应急链路特有手段，放应急页。
- 取证陷阱中，"SLS 分词漏检""停写数据源"已有通用规则（evidence-and-boundaries.md），不重复；仅把本地日常直连库 `stability-locate-daily-locatenew` 停写这一**具体已证实实例**补入 evidence-and-boundaries.md 的"文档 logstore ≠ 活 logstore"相邻位置，作为 DB 版同理提示。
- 误导性日志文案清单（`network fail` 误标、`{msg:null,code:"500"}`、页面"待发布"语义）是应急平台特有知识，放应急页「取证陷阱」小节。

### D5：不搬运案例全文

- 案例详情以报告文件名引用（`seek-report-*.md`），本仓库不复制全文，避免双源漂移。

## Risks / Trade-offs

- 案例表行数增长（+3）：可接受，表仍是单一速查入口。
- 方法论小节与 `investigation-patterns.md` 存在主题相邻：本变更只涉及应急平台案例，不动通知类页面；边界以"应急平台运行链相关"判断。
- `stability-locate/doc` 在工作区外，实施时不读取/修改这些文件，只按已汇总内容搬运。
