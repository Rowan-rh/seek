# Proposal: add-emergency-case-patterns

## Why

2026-08-26 ~ 09-01 期间通过 seek 完成了 6 例应急响应平台排查（流控卡单、模板 action 被删、autofix 待发布、detail/param 拆箱 NPE×2、objectService 填错），完整报告沉淀在 `stability-locate/doc/seek-report-*.md` 并已汇总为 `seek-reports-digest-2026-08-26-to-09-01.md`。其中 3 个故障模式（模板 action 被删、autofix start 瞬时故障双层无重试、方案参数缺 `primary` 拆箱 NPE）是既有故障模式库（`references/emergency-response-patterns.md`，CASE-001~010）未覆盖的新模式；另有一批可复用的归属方法论与取证陷阱（下游错误三分法、requestId 串联三日志、SLS 分词漏检、本地日常直连库停写等）尚未进入 references 知识页。不入库则下次同现象排查无法按指纹直接命中。

## What Changes

- `references/emergency-response-patterns.md` 的「已知故障模式快速匹配」表新增 3 条案例（编号续接现有序列：CASE-011、CASE-012、CASE-013），每条含故障指纹与核心结论，与既有行格式一致。
- 同文件补充「案例排查方法论」章节：四步定位归属法、requestId 串联三日志（无 trace 时的调用链闭环替代）、下游错误三分法、`aliyunpop dx` 深挖 POP 5xx。
- 同文件补充「取证陷阱」章节：连字符 uuid 关键词检索分词漏检须 SQL 全扫描兜底、本地配置的日常直连库为停写历史库（查不到 ≠ 不存在）、误导性日志文案清单（`network fail` 误标、`{msg:null,code:"500"}`、页面"待发布"语义）。
- 对 CASE-003 行追加占用方定性提示（令牌持有方可能是手动测试执行，须确认发起方式）。
- 对 CASE-004 行追加成因变体提示（指纹相同但成因可能是用户手动填参，非定位脚本错）。

## Capabilities

### New Capabilities
- `emergency-case-patterns`: 应急响应故障模式案例库（CASE 序列）的收录规则——案例条目四要素（指纹/根因/处置/检索入口）、编号续接不重号、指纹匹配时的成因变体标注、案例库与方法论/取证陷阱在 `references/emergency-response-patterns.md` 的沉淀位置。

### Modified Capabilities
（无——`openspec/specs` 下暂无本能力既有 spec）

## Impact

- **文档**：`references/emergency-response-patterns.md`（案例表 + 方法论/陷阱章节）；`SKILL.md` 的知识页索引行无需改动（已含"案例库"关键词）。
- **代码**：无。
- **配置/测试**：无。
- **外部依赖**：无。
- 案例详情全文仍保留在 `stability-locate/doc/seek-report-*.md`（工作区外，引用路径以文件名记录，不建立文件链接）。
