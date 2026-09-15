# Tasks: add-report-date-naming

## 1. 规范确立与文档更新

- [x] 1.1 `SKILL.md` 排查规则第 5 条增补报告落盘命名规范（单案例日期前缀 + digest 起止日期格式 + 平铺存放）
- [x] 1.2 `references/emergency-response-patterns.md`「新增案例详情」沉淀位置说明补命名格式；CASE-011~013 报告引用更新为带日期文件名（4 行 5 个文件名）

## 2. 存量迁移（stability-locate/doc/，工作区外）

- [x] 2.1 7 份单案例报告重命名为 `seek-report-YYYY-MM-DD-*`（日期取产出日，与 digest 案例表时间列核实一致）
- [x] 2.2 digest 重命名为 `seek-reports-digest-2026-08-26-to-2026-09-01.md`（结束日期补全 4 位年份）
- [x] 2.3 digest 内部 11 处报告文件名引用同步更新；核实 7 份单案例报告之间无交叉引用、L4 通配引用不受影响

## 3. Spec 落地

- [x] 3.1 `emergency-case-patterns` spec 新增「报告文件名携带产出日期」requirement（含新报告落盘、汇总文档命名两个 scenario）
- [x] 3.2 更新「案例库沉淀位置」requirement 的示例文件名为带日期版本
- [x] 3.3 `openspec validate add-report-date-naming --strict` 通过
- [x] 3.4 `openspec archive add-report-date-naming --yes`，确认 `openspec/specs/emergency-case-patterns/spec.md` 合并结果正确
