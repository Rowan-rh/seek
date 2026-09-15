# Tasks: add-emergency-case-patterns

## 1. 案例表新增三条

- [x] 1.1 `references/emergency-response-patterns.md`「已知故障模式快速匹配」表追加 CASE-011（模板 action 被删 → 详情查询恒定 500）、CASE-012（autofix 变更单创建后从未启动/待发布）、CASE-013（方案参数缺 `primary` → detail/param Boolean 拆箱 NPE）
- [x] 1.2 表后新增「新增案例详情（2026-08）」小节，三条案例各含指纹/根因/处置/检索入口四要素与报告文件名引用

## 2. 既有案例行追加更正

- [x] 2.1 CASE-003 行追加：令牌持有方可能是手动测试执行，须确认发起方式；止血可调 `POST /decision/recovery` 传持有方 estask uuid
- [x] 2.2 CASE-004 行追加：成因变体——用户手动填错 `objectService`（如 `cgw` vs `cgw-service#sna`）与定位脚本选错字段指纹相同，先区分成因再定归属

## 3. 方法论与取证陷阱小节

- [x] 3.1 应急页新增「案例排查方法论」小节：四步定位归属法、requestId 串联三日志（堆栈取 `log` 字段）、下游错误三分法、`aliyunpop dx` 深挖 POP 5xx
- [x] 3.2 应急页新增「取证陷阱」小节：误导性文案清单（`Call change request, network fail` 误标、`{msg:null,code:"500"}` 切面二次 NPE、页面"待发布"≠未提交）、环境路由以访问日志 VIP 为准、"谁发起"定性须有操作人直证
- [x] 3.3 `references/evidence-and-boundaries.md` 补一条具体实例：本地直连日常库（`stability-locate-daily-locatenew`）已证实停写（`max(gmt_created)` 停在 2025 年），查不到 ≠ 不存在，用 `SELECT MAX(gmt_created)` 判定

## 4. 一致性检查与归档

- [x] 4.1 确认 `SKILL.md` 知识页索引行已覆盖（无需改动）；全文检索无 `CASE-009 候选` 等冲突编号残留
- [x] 4.2 `openspec validate add-emergency-case-patterns --strict` 通过
- [x] 4.3 `openspec archive add-emergency-case-patterns --yes`，确认 `openspec/specs/emergency-case-patterns/spec.md` 生成
