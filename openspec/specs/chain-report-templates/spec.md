# chain-report-templates Specification

## Purpose
定义排查报告模板的存放结构、链路绑定与解析规则，使每条排查链路在产出报告时都有结构化模板可依，且用户可按需覆盖模板。

## Requirements

### Requirement: 内置报告模板集合
系统 SHALL 内置两份报告模板：`generic.md`（通用排查报告模板，适用于所有非工单场景）与 `ticket.md`（云网络工单专用模板，含 flowId、工单分类、相似工单、转单建议等工单独有章节）。两份模板 MUST 随 CLI 打包分发。对于故障型报告，两份模板 MUST 包含异常样本与正常样本横向对比，并区分直接报错点、首要触发根因和次生容错或放大问题。

#### Scenario: 通用模板包含必备章节
- **WHEN** 读取内置 `generic.md`
- **THEN** 包含以下章节：快速结论、可复用排查路径与证据点、排查过程、样本对比与归因、根因分析、修复建议、未决事项、更正记录
- **AND** 不引用 flowId、questionTitle 等工单独有占位符

#### Scenario: 工单模板保留工单结构
- **WHEN** 读取内置 `ticket.md`
- **THEN** 保留工单信息、相似工单分析、推荐联系人、通知类固定证据项等工单独有章节
- **AND** 包含样本对比与分层归因字段

#### Scenario: 缺少对照证据时限制确定性表述
- **WHEN** 故障报告无法提供可比正常样本、直接复现或数据修正前后验证
- **THEN** 模板要求将根因结论标记为证据不足
- **AND** 禁止仅凭异常堆栈使用“代码级确定性缺陷”或“数据级确定性异常”表述

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

### Requirement: 报告文件名与头部构造入口
系统 SHALL 提供 `seek chain report <session> --slug <语义段>` 命令，对状态为 completed 的会话构造报告落盘要素：带产出日期前缀的文件名（`seek-report-YYYY-MM-DD-{slug}.md`，日期为命令执行日）、已填充机器可确定字段的模板头部 markdown 与报告模板解析结果（name/path）。该命令 MUST NOT 写入任何文件——落盘由调用方完成。

#### Scenario: completed 会话生成报告文件名与头部
- **WHEN** 对状态为 completed 的会话执行 `seek chain report <session> --slug "batch-560d6f3c-objectlist-empty"`
- **THEN** 返回 `filename` 形如 `seek-report-2026-09-02-batch-560d6f3c-objectlist-empty.md`（日期为当日）
- **AND** 返回 `header_markdown` 中 `{session_id}`/`{chain_name}`/`{start_time}`/`{end_time}`/`{problem_description}` 已替换为会话实际值，语义占位符（如 `{主题一句话}`、`{flowId}`）保持原样
- **AND** 返回 `template` 含解析后的模板名与绝对路径

#### Scenario: 未完成会话拒绝生成
- **WHEN** 对状态非 completed 的会话执行 `seek chain report`
- **THEN** 返回错误（`SESSION_NOT_COMPLETED`），不生成文件名与头部

#### Scenario: slug 格式非法拒绝
- **WHEN** `--slug` 为空、含大写/空格/下划线、超过 80 字符，或自带 `seek-report` 前缀、`YYYY-MM-DD` 日期前缀、`.md` 后缀
- **THEN** 返回错误（`BAD_SLUG`），错误信息说明合法格式（小写 kebab-case 语义段，如 `batch-560d6f3c-objectlist-empty`）

#### Scenario: 会话不存在
- **WHEN** 对不存在的会话 ID 执行 `seek chain report`
- **THEN** 返回错误（`NOT_FOUND`）
