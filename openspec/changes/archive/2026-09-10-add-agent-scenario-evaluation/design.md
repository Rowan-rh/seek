# Design: add-agent-scenario-evaluation

## Context

真实 Agent 的执行环境和模型可能变化，CI 又必须确定性、离线、可复现。因此评测核心与执行器解耦：同一场景可消费录制结果，也可由外部 runner 实时生成结果。

## Goals / Non-Goals

**Goals:** 覆盖协议、轨迹、报告三层；稳定定位违规；支持真实 Agent；提供 20～30 个脱敏基线案例；离线 CI 可重复。

**Non-Goals:** 不在仓库中绑定特定模型 SDK，不以 LLM-as-judge 替代确定性断言，不访问生产系统。

## Decisions

- 场景文件使用版本化 JSON，包含 defaults、scenarios、expected 和 replay。
- `replay` 模式读取场景内已录制结果；`live` 模式对每个场景执行 `--agent-command`，通过 stdin 传入场景 JSON，并从 stdout 读取结果 JSON。
- 禁止 shell 执行：命令使用 `shlex.split` 后由 subprocess 直接启动。
- 评分输出按 protocol/trajectory/report 分层，每项返回稳定 violation code。
- evidence reference 只能引用状态为 success/empty/partial 的工具调用；timeout、permission-denied 等失败调用不能支撑根因。
- 提示词注入案例要求结果显式声明未遵从注入内容。
- replay 纳入默认门禁；live 模式由具备 Agent 和凭据的环境显式运行。

## Risks / Trade-offs

- 结构化断言无法覆盖所有语言质量 → 当前阶段优先保证可重复的事实性门禁，后续可增加人工或模型裁判。
- replay 不能证明当前模型表现 → 报告明确标注 mode，真实发布评测应使用 live runner。
- 不同 Agent 启动方式不同 → 使用 stdin/stdout JSON 的最小适配协议隔离差异。
