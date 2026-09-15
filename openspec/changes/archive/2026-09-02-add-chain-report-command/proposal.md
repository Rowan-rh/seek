# Proposal: add-chain-report-command

## Why

报告文件命名规范（emergency-case-patterns 的「报告文件名携带产出日期」requirement）目前只靠 SKILL.md 文档约束 agent 自觉执行：日期取值、前缀拼接、kebab-case 格式全部由 agent 手写，存在抄错日期、格式漂移的敞口；报告头部的 session_id/起止时间/问题描述也是 agent 从 `chain context` 输出手工转录的。链路引擎的设计哲学是"引擎校验每个状态转换，agent 只供内容"，而报告落盘是链路生命周期中唯一零引擎介入的环节。把文件名的机械部分（日期前缀、格式校验）与头部转录收敛为 CLI 构造入口，正确路径即最省力路径。

## What Changes

- 新增 `seek chain report <session> --slug <语义段>` 子命令：校验会话为 completed 后，返回带产出日期前缀的报告文件名（`seek-report-YYYY-MM-DD-{slug}.md`）、已填充机器可确定字段的模板头部 markdown 与模板路径；CLI 不落盘（保持"CLI 不写用户文件"边界，由 agent 写入目标目录）。
- slug 校验：小写 kebab-case 段（`[a-z0-9]+(-[a-z0-9]+)*`，≤80 字符），拒绝携带 `seek-report` 前缀、`YYYY-MM-DD` 日期前缀或 `.md` 后缀（防双重前缀），拒绝空值。
- 头部渲染：读取模板（用户覆盖→内置解析链复用 `get_report_template`）首个 `---` 分隔线之前的头部块，替换 `{session_id}`/`{chain_name}`/`{start_time}`/`{end_time}`/`{problem_description}` 为会话实际值；`{主题一句话}`、`{flowId}` 等语义占位符保留给 agent。
- 同步更新：capabilities 登记、SKILL.md 规则 5 与执行协议 Step 8、references/command-reference.md、CHANGELOG（版本 0.4.0→0.4.1）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `chain-report-templates`: 新增「报告文件名与头部构造入口」requirement —— `chain report` 命令的输出契约（filename/header_markdown/template）、completed 会话前置校验与 slug 格式校验。

## Impact

- **文档**：`SKILL.md`（规则 5、执行协议、cli_version_ref）、`references/command-reference.md`、`seek_cli/__init__.py` CHANGELOG。
- **代码**：`cli/seek_cli/chain.py`（引擎新增 slug 校验/报告构造函数）、`cli/seek_cli/commands/chain.py`（cmd_chain_report）、`cli/seek_cli/cli.py`（parser 与 docstring）、`cli/seek_cli/commands/capabilities.py`（登记）。
- **配置/测试**：新增 `cli/tests/test_chain_report.py`；capabilities 契约测试自动覆盖新子命令参数一致性。
- **外部依赖**：无。`emergency-case-patterns` 的命名规范 requirement 不变，本变更是其机器化执行入口。
