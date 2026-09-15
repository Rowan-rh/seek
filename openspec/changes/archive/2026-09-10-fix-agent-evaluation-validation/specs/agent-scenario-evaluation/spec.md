## MODIFIED Requirements

### Requirement: 版本化场景与 runner 协议
系统 SHALL 从版本化 JSON 场景集中读取脱敏输入与期望，并支持 replay 和 live 两种模式。场景及 expected 的已声明容器和标量字段 MUST 在执行前完成类型校验，非法输入 MUST 返回结构化配置错误。live 模式 MUST 通过 stdin 向外部 Agent 命令传递单个场景的执行字段，但 MUST 排除 replay 和 expected 评分标准；命令 MUST 不经 shell 执行。

#### Scenario: 离线回放
- **WHEN** 未提供外部 Agent 命令
- **THEN** 评测器使用场景内 replay 结果
- **AND** 报告明确标记 `mode=replay`

#### Scenario: 真实 Agent 执行
- **WHEN** 提供 `--agent-command`
- **THEN** 每个场景实际启动该命令并传入不含评分标准的执行输入 JSON
- **AND** 报告明确标记 `mode=live`

#### Scenario: 畸形 expected 输入
- **WHEN** defaults.expected、scenario.expected 或已声明的 expected 子字段类型非法
- **THEN** 返回 AGENT_EVAL_CONFIG_ERROR
- **AND** 不抛出 AttributeError、TypeError 或非 JSON traceback

#### Scenario: 真实 Agent 执行不泄漏评分标准
- **WHEN** 提供 `--agent-command`
- **THEN** runner stdin 包含场景标识、提示和 fixture 等执行输入
- **AND** 不包含 replay 或 expected

### Requirement: 三层确定性评测
评测器 SHALL 分别评估 protocol、trajectory 和 report，并为失败断言返回稳定 violation code。任一必选断言失败时场景 MUST 失败，任一场景失败时总评 MUST 失败并返回非零退出码。汇总 SHALL 使用 `scenario_failure_rate` 表达失败场景占比，使用 `violations_per_scenario` 表达平均违规条数；旧 `constraint_violation_rate` MAY 作为兼容别名保留，但 MUST 标记为 deprecated。

#### Scenario: 轨迹存在冗余或错误工具调用
- **WHEN** Agent 超过工具预算、重复调用或调用 forbidden tool
- **THEN** trajectory 层失败并报告对应违规码

#### Scenario: 报告引用无效证据
- **WHEN** 根因或声明引用不存在或失败工具调用产生的 evidence id
- **THEN** report 层失败并报告无效证据引用

#### Scenario: 指标名称与口径明确
- **WHEN** 一个场景产生多条违规
- **THEN** scenario_failure_rate 仍按失败场景数计算
- **AND** violations_per_scenario 按违规总数除以场景数计算
- **AND** 兼容别名不会被描述为单条约束的失败概率
