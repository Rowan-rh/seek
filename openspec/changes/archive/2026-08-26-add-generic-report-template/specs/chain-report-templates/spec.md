# Delta: chain-report-templates

## Purpose

定义排查报告模板的存放结构、链路绑定与解析规则，使每条排查链路在产出报告时都有结构化模板可依，且用户可按需覆盖模板。

## ADDED Requirements

### Requirement: 内置报告模板集合
系统 SHALL 内置两份报告模板：`generic.md`（通用排查报告模板，适用于所有非工单场景）与 `ticket.md`（云网络工单专用模板，含 flowId、工单分类、相似工单、转单建议等工单独有章节）。两份模板 MUST 随 CLI 打包分发。

#### Scenario: 通用模板包含必备章节
- **WHEN** 读取内置 `generic.md`
- **THEN** 包含以下章节：快速结论、可复用排查路径与证据点、排查过程、根因分析、修复建议、未决事项、更正记录
- **AND** 不引用 flowId、questionTitle 等工单独有占位符

#### Scenario: 工单模板保留工单结构
- **WHEN** 读取内置 `ticket.md`
- **THEN** 保留原 `cli/chains/report-template.md` 的章节结构（工单信息、相似工单分析、推荐联系人、通知类固定证据项等）

### Requirement: 链路通过 reportTemplate 字段绑定模板
链路定义 SHALL 支持可选顶层字段 `reportTemplate`，值为模板文件名（如 `ticket.md`）。未声明该字段的链路 MUST 默认绑定 `generic.md`。

#### Scenario: alert-ticket 显式绑定工单模板
- **WHEN** 查询 `alert-ticket` 链路的报告模板
- **THEN** 解析结果为 `ticket.md`

#### Scenario: 未声明字段回退通用模板
- **WHEN** 查询任意未声明 `reportTemplate` 的链路（如 `default`、`notification`、`emergency-response`）的报告模板
- **THEN** 解析结果为 `generic.md`

#### Scenario: 声明不存在的模板报错
- **WHEN** 查询一条 `reportTemplate` 指向不存在文件的链路
- **THEN** 解析失败并返回可诊断的错误（含模板文件名与搜索路径），不得静默回退

### Requirement: 用户模板覆盖优先
系统 SHALL 按「用户覆盖目录（~/.seek/chains/templates/）→ 内置模板」的顺序解析模板；同名文件时用户版本优先。

#### Scenario: 用户覆盖生效
- **WHEN** 用户在 ~/.seek/chains/templates/generic.md 放置同名模板
- **THEN** 解析结果返回用户文件路径

### Requirement: 模板解析结果对 agent 可见
`seek chain list` 与 `seek chain context` 的输出 SHALL 包含当前链路的报告模板信息（模板文件名与可读取的绝对路径），agent 无需猜测路径即可读取模板生成报告。

#### Scenario: chain context 输出模板路径
- **WHEN** 对任意会话执行 `seek chain context <session>`
- **THEN** 输出 JSON 包含 `report_template` 字段，含 `name` 与 `path`，且 `path` 指向实际存在的文件

#### Scenario: chain list 输出模板名
- **WHEN** 执行 `seek chain list`
- **THEN** 每条链路条目包含 `reportTemplate` 字段
