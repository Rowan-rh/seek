# Proposal: add-report-date-naming

## Why

排查报告全文沉淀在 `stability-locate/doc/`（工作区外），存量 8 份文件名均不带日期：单案例为 `seek-report-{场景}-{ID}-{现象}.md` 三段式，digest 汇总 `seek-reports-digest-2026-08-26-to-09-01.md` 的结束日期还缺 4 位年份。平铺目录下文件无法按时间排序与分类；且命名规则只是隐性实践，SKILL.md 与报告模板均未规定，新报告产出无成文依据，容易漂移出第三种命名。不改则目录规模增长后新旧命名混排，分类与检索价值持续衰减。

## What Changes

- 确立报告文件命名规范：单案例以产出日期为前缀 `seek-report-YYYY-MM-DD-{场景}-{业务ID片段?}-{现象}.md`（无唯一业务标识时省略 ID 段）；多篇汇总 `seek-reports-digest-YYYY-MM-DD-to-YYYY-MM-DD.md`（起止日期均为 4 位年份）；同目录平铺存放，不按日期建子目录。
- 存量 8 份报告全部迁移到新命名（含 digest 结束日期补全年份），并同步更新全部文件名引用：`references/emergency-response-patterns.md`（CASE-011~013 案例报告引用 + 沉淀位置说明）、digest 文档内部交叉引用（11 处）。
- `SKILL.md` 排查规则第 5 条增补报告落盘命名规范。
- `emergency-case-patterns` spec 新增「报告文件名携带产出日期」requirement，并更新既有「案例库沉淀位置」requirement 中的示例文件名。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `emergency-case-patterns`: 新增报告文件命名规范 requirement（日期前缀、汇总格式、平铺存放），并更新「案例库沉淀位置」requirement 的示例文件名为带日期版本。

## Impact

- **文档**：`SKILL.md`、`references/emergency-response-patterns.md`、`openspec/specs/emergency-case-patterns/spec.md`、`stability-locate/doc/` 下 8 份存量报告文件名及 digest 内部交叉引用。
- **代码**：无（CLI 不生成报告文件，命名约束作用于 agent 落盘行为）。
- **配置/测试**：无。
- **外部依赖**：无。
- 归档目录 `openspec/changes/archive/` 中出现过的旧文件名作为历史快照不改写。
