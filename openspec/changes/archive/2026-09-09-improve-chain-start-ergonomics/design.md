# Design: improve-chain-start-ergonomics

## D1. 首步外部输入的计算

引擎新增 `first_step_external_inputs(chain_name)`：

- 取链路 step 1 的 `requiredInputs`，剔除有声明生产步骤（`_declared_output_producers`）的键，剩余即"外部输入"——只能在会话启动阶段由 `--context`/`--problem` 提供。
- 链路不存在时抛 `ValueError`（与 `start_session` 一致）。

`list_chains()` 每个链路条目新增 `firstStepInputs` 字段（该函数的输出），使 `chain list` 与 `capabilities.chains` 自动暴露，agent 可在 start 前发现所需键名。

## D2. `chain start` 前置校验

`cmd_chain_start` 在调用 `start_session` 之前：

1. 先 `get_chain(args.name)`，不存在直接返回 error（code=`CHAIN_NOT_FOUND`），不再进入建会话流程。
2. 保留现有 `--context` JSON 解析与"键名与步骤名冲突"检查。
3. 计算缺失输入：`missing = [k for k in first_step_external_inputs(name) if k not in initial_context and not (k in _PROBLEM_DESCRIPTION_INPUTS and problem 非空)]`。
4. 若 missing 非空，返回 error（code=`MISSING_CONTEXT`，退出码非零），data 含：
   - `missing_inputs`: 缺失键名列表
   - `required_inputs`: 该链路首步全部外部输入
   - `hint`: 说明 `--context` 注入方式与 `--problem` 可满足的描述型键名（`_PROBLEM_DESCRIPTION_INPUTS` 交集）

错误消息格式示例：
`chain 'emergency-stuck-task' step 1 requires inputs not provided: ['task_id_or_description']`

会话文件不落盘，杜绝废弃会话。

## D3. `chain provide` 补注入

引擎新增 `provide_inputs(session_id, inputs)`：

- 会话不存在抛 `ValueError`；`completed` 状态拒绝（补注入只服务未完成会话的首步输入）。
- 键名与该链路任一步骤名冲突时抛 `ValueError`（与 start 的 `--context` 冲突语义一致，防 complete 时命名空间覆盖）。
- merge 进 `session["context"]` 顶层（与 `start --context` 平铺语义一致），原子保存。

命令 `cmd_chain_provide`：

- `--inputs` 必填，JSON 对象校验（code=`BAD_JSON`）。
- 成功后返回注入的键列表，并附当前步骤（注入后的 `current_step`）的 `validate_step` 结果，让调用方立即确认输入已满足。

CLI 注册 `chain provide <session> --inputs '{...}'`；capabilities.py chain 段同步声明（契约测试要求 argparse 与 capabilities 逐字对齐）。

## D4. SKILL.md 链路表"首步输入"列

内置链路表新增一列，内容以 `chain list` 的 `firstStepInputs` 为准：

| 链路 | 首步输入 |
|------|----------|
| default / notification / cron-task-health / emergency-response / emergency-stuck-task | `--problem` 描述即可（描述型输入豁免） |
| alert-enrichment | `--context '{"alert_uuid_or_endpoint":"..."}'` |
| alert-ticket | `--context '{"flow_id":"FLOW-xxx"}'` |

执行协议 Step 1 补充：缺键时 start 直接报错（`MISSING_CONTEXT`）；已建会话可用 `chain provide` 补注入。

## D5. 兼容性与边界

- 键名齐全的既有调用路径行为不变（校验 missing 为空，直接建会话）。
- `--context` 中与首步输入无关的额外键不报错（允许注入补充信息），仅步骤名冲突才拒绝。
- `provide` 允许在任意未完成阶段注入（不限制 current_step==1），因为后续步骤的 requiredInputs 校验只认声明生产者，顶层 context 注入只对无生产者的外部输入生效，无绕过风险。

## D6. 测试策略

- `test_chain_start_inputs.py`：覆盖 start 缺键阻断（error 态 + missing/required 列表 + 不落盘）、`--problem` 豁免、键名齐全放行、provide 补注入后 validate 通过、provide 冲突/已完成会话/坏 JSON 拒绝、`firstStepInputs` 字段。
- `test_capabilities_contract.py`：provide 子命令进入契约比对，自动通过参数集逐字对齐。
- 既有 103+ 测试回归全绿。
