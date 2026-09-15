# Delta: chain-session-inputs

## Purpose

定义链路会话首步外部输入的发现、前置校验与补注入规则，让调用方在建会话前就能知道并满足首步所需输入，避免产生废弃会话；会话建立后也提供补救注入手段。

## ADDED Requirements

### Requirement: 首步外部输入可发现
系统 SHALL 为每条链路计算"首步外部输入"——首步 `requiredInputs` 中没有任何声明生产步骤的键。`chain list` 与 `capabilities` 输出的每个链路条目 MUST 包含 `firstStepInputs` 字段，列出这些键名。

#### Scenario: 无生产者的输入被列为外部输入
- **WHEN** 查询 `alert-ticket` 链路的摘要
- **THEN** `firstStepInputs` 包含 `flow_id`（首步无声明生产步骤）

#### Scenario: 有生产者的输入不列为外部输入
- **WHEN** 某链路首步的一个 requiredInput 同时是后续/前序步骤声明的 output
- **THEN** 该键不进入 `firstStepInputs`

### Requirement: chain start 前置校验首步输入
系统 SHALL 在 `chain start` 创建会话之前校验首步外部输入是否已被 `--context` 或 `--problem` 满足；存在缺失时 MUST 返回 error 态（进程退出码非零），且不得落盘会话文件。错误 data MUST 包含 `missing_inputs`（缺失键）、`required_inputs`（该链路首步全部外部输入）与 `hint`。

#### Scenario: 缺键时阻断建会话
- **WHEN** 执行 `chain start alert-ticket` 且未通过 `--context` 提供 `flow_id`
- **THEN** 返回 error，code 为 `MISSING_CONTEXT`，data.missing_inputs 含 `flow_id`
- **AND** 不创建会话文件

#### Scenario: 描述型输入可被 --problem 满足
- **WHEN** 执行 `chain start emergency-stuck-task --problem "<非空描述>"`，首步外部输入为 `task_id_or_description`（属描述型豁免集合）
- **THEN** 校验通过并创建会话

#### Scenario: 键名齐全放行
- **WHEN** 执行 `chain start alert-ticket --context '{"flow_id":"FLOW-xxx"}'`
- **THEN** 正常创建会话，行为与既有一致

#### Scenario: 额外键不报错
- **WHEN** `--context` 含首步输入之外的补充键（且不与步骤名冲突）
- **THEN** 不因额外键阻断建会话

### Requirement: chain provide 补注入
系统 SHALL 提供 `chain provide <session> --inputs '{...}'`，将输入 merge 进未完成会话的 context 顶层（与 `start --context` 平铺语义一致），并在注入后返回当前步骤的 validate 结果。

#### Scenario: 补注入后校验通过
- **WHEN** 对缺键建立的会话执行 `chain provide <session> --inputs '{"flow_id":"FLOW-xxx"}'`
- **THEN** 输入写入 context 顶层，返回的 validate 结果对当前步骤为 valid

#### Scenario: 已完成会话拒绝补注入
- **WHEN** 对 status 为 `completed` 的会话执行 `chain provide`
- **THEN** 返回 error，不修改会话

#### Scenario: 键名与步骤名冲突拒绝
- **WHEN** `--inputs` 中某键与该链路任一步骤名同名
- **THEN** 返回 error，不写入 context

#### Scenario: 非法 JSON 拒绝
- **WHEN** `--inputs` 不是合法 JSON 对象
- **THEN** 返回 error，code 为 `BAD_JSON`
