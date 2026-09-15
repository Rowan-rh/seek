# Proposal: add-generic-report-template

## Why

目前仓库只有一个排查报告模板 `cli/chains/report-template.md`，且被 `alert-ticket` 链路硬编码引用，整体结构围绕云网络工单（flowId、工单分类、相似工单、转单建议）设计。其余 6 条链路（default、alert-enrichment、notification、cron-task-health、emergency-response、emergency-stuck-task）的最终报告只靠 agentInstructions 文字约束自由生成，而 SKILL.md 又要求所有链路报告包含"可复用排查路径与证据点"章节——形成"有要求、无模板"的状态，报告结构不稳定、不可复用。

## What Changes

- 新增**通用排查报告模板** `generic.md`，适配非工单场景（无 flowId/工单字段），保留 SKILL.md 要求的核心章节：快速结论、可复用排查路径与证据点、排查过程、根因分析、修复建议、未决事项、更正记录。
- 现有 `report-template.md` 更名为 `ticket.md`，语义明确为"云网络工单专用模板"（**BREAKING**：路径变更，仅影响引用该路径的文档与测试）。
- 链路定义新增可选字段 `reportTemplate`：显式指定模板文件名；未声明时回退到 `generic.md`。`alert-ticket` 显式声明 `ticket.md`，其余链路走默认。
- chain 引擎新增模板解析能力 `get_report_template(chain_name)`：按 用户覆盖目录（~/.seek/chains/templates/）→ 内置模板 的顺序解析；解析结果（模板名+绝对路径）注入 `chain context` 输出与 `chain list` 输出，供 agent 出报告时直接读取。
- `setup.py` package_data 补齐模板文件打包。
- 同步文档：SKILL.md、cli/README.md、各链路末步 agentInstructions 指向模板解析机制。

## Capabilities

### New Capabilities
- `chain-report-templates`: 排查报告模板的存放、解析与链路绑定规则——模板目录结构、`reportTemplate` 字段语义、用户覆盖优先、缺省回退 generic、通过 `chain context`/`chain list` 暴露解析结果。

### Modified Capabilities
（无——本仓库 openspec/specs 下暂无既有 spec）

## Impact

- **代码**：`cli/seek_cli/chain.py`（模板解析）、`cli/seek_cli/commands/chain.py`（context/list 输出）、`cli/setup.py`（package_data）。
- **配置**：`cli/chains/default.json` 与 `cli/seek_cli/resources/chains/default.json`（两份需保持同步）新增 `reportTemplate` 字段。
- **文件移动**：`cli/chains/report-template.md` → `cli/chains/templates/ticket.md`；新增 `cli/chains/templates/generic.md`。
- **测试**：`cli/tests/test_documentation.py`（更新路径引用）、新增 `cli/tests/test_report_templates.py`。
- **文档**：`SKILL.md`、`cli/README.md`。
- 无外部依赖变化，无 CLI 命令签名变化（纯输出字段新增）。
