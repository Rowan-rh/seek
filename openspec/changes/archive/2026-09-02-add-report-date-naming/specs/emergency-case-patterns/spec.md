# emergency-case-patterns Specification (Delta)

## ADDED Requirements

### Requirement: 报告文件名携带产出日期
案例全文报告的落盘文件名 SHALL 以产出日期为前缀：单案例 `seek-report-YYYY-MM-DD-{场景}-{业务ID片段}-{现象}.md`（无唯一业务标识时省略 ID 段），多篇汇总 `seek-reports-digest-YYYY-MM-DD-to-YYYY-MM-DD.md`（起止日期均为 4 位年份）。报告 SHALL 与既有报告同目录平铺存放，MUST NOT 按日期建子目录归档。

#### Scenario: 新报告落盘
- **WHEN** 一次排查完成并产出报告全文
- **THEN** 文件名形如 `seek-report-2026-09-02-batch-560d6f3c-objectlist-empty.md`（日期为报告产出日），与既有报告同目录平铺存放

#### Scenario: 汇总文档命名
- **WHEN** 多份报告整理为 digest 汇总文档
- **THEN** 文件名形如 `seek-reports-digest-2026-08-26-to-2026-09-01.md`，起止日期均为 4 位年份

## MODIFIED Requirements

### Requirement: 案例库沉淀位置
新增故障模式、案例排查方法论与取证陷阱 SHALL 沉淀至 `references/emergency-response-patterns.md`。案例全文报告不进入本仓库，仅在案例条目中以报告文件名引用（如 `seek-report-2026-08-27-template-action-deleted.md`，命名遵循「报告文件名携带产出日期」）。

#### Scenario: 新故障模式入库
- **WHEN** 一次排查确认了既有案例库未覆盖的故障模式
- **THEN** 在 `references/emergency-response-patterns.md` 的「已知故障模式快速匹配」表中新增对应案例行
- **AND** 案例详情报告以文件名形式被引用，不复制全文进本仓库
