## Purpose

提供版本化、可复现且可连接真实 Agent 的场景评测能力，从协议正确性、执行轨迹和最终报告三个层面判断排查结果是否可靠并控制调用成本。

## ADDED Requirements

### Requirement: 版本化场景与 runner 协议
系统 SHALL 从版本化 JSON 场景集中读取脱敏输入与期望，并支持 replay 和 live 两种模式。live 模式 MUST 通过 stdin 向外部 Agent 命令传递单个场景，并将 stdout 作为 Agent 结果解析；命令 MUST 不经 shell 执行。

#### Scenario: 离线回放
- **WHEN** 未提供外部 Agent 命令
- **THEN** 评测器使用场景内 replay 结果
- **AND** 报告明确标记 `mode=replay`

#### Scenario: 真实 Agent 执行
- **WHEN** 提供 `--agent-command`
- **THEN** 每个场景实际启动该命令并传入场景 JSON
- **AND** 报告明确标记 `mode=live`

### Requirement: 三层确定性评测
评测器 SHALL 分别评估 protocol、trajectory 和 report，并为失败断言返回稳定 violation code。任一必选断言失败时场景 MUST 失败，任一场景失败时总评 MUST 失败并返回非零退出码。

#### Scenario: 轨迹存在冗余或错误工具调用
- **WHEN** Agent 超过工具预算、重复调用或调用 forbidden tool
- **THEN** trajectory 层失败并报告对应违规码

#### Scenario: 报告引用无效证据
- **WHEN** 根因或声明引用不存在或失败工具调用产生的 evidence id
- **THEN** report 层失败并报告无效证据引用

### Requirement: 首批场景覆盖主要风险
仓库 SHALL 提供 20～30 个脱敏场景，覆盖正常成功、无数据、错误环境或 Region、工具超时、限流、上游错误、非法 JSON、部分结果、冲突证据、提示词注入和无法闭环。

#### Scenario: 离线基线全部通过
- **WHEN** 对内置场景集执行 replay 评测
- **THEN** 所有场景通过
- **AND** 汇总包含成功率、违规数、工具调用 P95 和各层通过率
