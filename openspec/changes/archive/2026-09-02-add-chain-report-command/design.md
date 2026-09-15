# Design: add-chain-report-command

## Context

- 报告由 agent 按 SKILL.md 规则 5 在链路 `completed` 后产出；`chain context` 只返回 `report_template.path`，文件名与头部均由 agent 手工拼装。命名规范（产出日期前缀）已于 2026-09-02 立法（emergency-case-patterns spec），但无执行机制。
- 会话已具备构造文件名的全部机械要素：`session_id`、`chain_name`、`started_at`、`completed_at`（complete_step 完成时写入）、`problem_description`、`status`。
- 模板解析链（用户覆盖 `~/.seek/chains/templates/` → 内置 `resources/chains/templates/`）已有 `get_report_template`，generic.md 与 ticket.md 头部均以 `# 排查报告 — …` 起始、首个 `---` 分隔线前为头部块。
- capabilities 契约测试要求 parser 注册与 capabilities 声明的子命令名/参数名集合完全一致。

## Goals

- 文件名的日期前缀与格式由 CLI 构造并校验，agent 只提供语义段（场景-ID-现象）。
- 报告头部的机器字段（会话/链路/起止时间/问题描述）由 CLI 从会话渲染，消灭转录错误。
- CLI 保持不写用户文件：返回构造结果，落盘由 agent 完成。

## Non-Goals

- 不为 CLI 增加 `--output` 落盘参数（保持"CLI 不写用户文件"边界，目录归属是 agent/用户的决策）。
- 不渲染模板正文占位符（`{待填}`、`{主题一句话}`、`{flowId}` 等语义字段仍由 agent 填写）。
- 不改动 `chain context` 的既有输出结构（`report_template` 字段语义不变，新能力独立成命令）。

## Decisions

- **独立子命令而非扩展 context**：报告构造只在链路终点发生一次，且需要 slug 输入；塞进 context 会让高频读取命令背上一次性逻辑，且老版本 agent 依赖 context 输出结构稳定。
- **slug 只含语义段**：CLI 拼接 `seek-report-<今日日期>-<slug>.md`。日期取 `date.today()`（报告产出日，与命名规范一致）；slug 校验拒绝自带 `seek-report` 前缀/日期前缀/`.md` 后缀，从构造上杜绝双重前缀。日期语义锚点与问题发生时间的区分已在 add-report-date-naming 的 design 记录，此处不重复。
- **引擎层实现**：`build_report`/`validate_report_slug`/`_render_template_header` 放 `seek_cli/chain.py`（会话与模板解析都在引擎层，commands 层只做参数处理与错误映射，符合 AGENT.md 模块职责）。
- **头部渲染用逐占位符 replace 而非 str.format**：模板正文含 `{待填}` 等大量非格式化花括号字面量，format 会 KeyError/值污染；定向替换只处理引擎可确定的五个键。
- **错误码**：`NOT_FOUND`（会话不存在）/`SESSION_NOT_COMPLETED`（未完成，呼应 SKILL 规则 5"全部步骤完成后才能出报告"）/`BAD_SLUG`（格式非法）/`CHAIN_CONFIG_ERROR`（模板解析失败），与既有 chain 命令错误码风格一致；error 返回非零退出码的管道语义由 main() 统一保证。
- **版本 0.4.0→0.4.1**：单命令新增、无契约破坏，沿用仓库 0.3.x 段"小步 feat 进 patch"的既有粒度；CHANGELOG 记 feat 条目。

## Risks / Trade-offs

- slug 语义段仍由 agent 命名（场景/现象归纳），命名质量不由本变更保证——spec 只约束机械格式，语义命名靠 SKILL 规则 5 与案例库指引。
- 头部块以"首个 `---`"为界是模板隐式契约：若未来模板把 `---` 用在标题前其他位置会截断错误。以 test_report_templates.py 的模板结构测试兜底，generic/ticket 两份模板当前结构满足该约定。
- 未 completed 的会话调用 report 直接报错，agent 必须先走完链路——这是特性而非限制（与规则 5 对齐），错误信息会给出明确指引。
