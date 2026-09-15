# Tasks: improve-chain-start-ergonomics

## 1. 引擎能力（cli/seek_cli/chain.py）

- [x] 1.1 新增 `first_step_external_inputs(chain_name)`：返回首步无生产者的 requiredInputs（链路不存在抛 ValueError）
- [x] 1.2 新增 `missing_start_inputs(chain_name, initial_context, problem_description)`：计算缺失输入（`_PROBLEM_DESCRIPTION_INPUTS` + 非空 `--problem` 视为满足）
- [x] 1.3 `list_chains()` 条目新增 `firstStepInputs` 字段
- [x] 1.4 新增 `provide_inputs(session_id, inputs)`：未完成会话校验、步骤名冲突拒绝、merge 进 context 顶层并原子保存

## 2. 命令与 CLI 注册

- [x] 2.1 `commands/chain.py`：`cmd_chain_start` 建会话前做缺键前置校验，缺键返回 error（code=`MISSING_CONTEXT`，data 含 missing_inputs/required_inputs/hint），会话不落盘
- [x] 2.2 `commands/chain.py`：新增 `cmd_chain_provide`（--inputs JSON 校验 + 调用引擎 + 附当前步骤 validate 结果）
- [x] 2.3 `cli.py`：注册 `chain provide <session> --inputs` 子命令并更新模块 docstring 用法
- [x] 2.4 `capabilities.py`：chain 段新增 provide 子命令声明（与 argparse 逐字对齐）

## 3. 测试

- [x] 3.1 新建 `cli/tests/test_chain_start_inputs.py`：start 缺键阻断/豁免/放行、provide 补注入与拒绝路径、firstStepInputs 字段
- [x] 3.2 运行 `python -m unittest discover cli/tests` 全绿（含 capabilities 契约测试）

## 4. 文档与验证

- [x] 4.1 `SKILL.md`：链路表加"首步输入"列；执行协议补 provide 与 MISSING_CONTEXT 说明
- [x] 4.2 `cli/README.md`、`references/command-reference.md`：补 `chain provide` 用法与错误码
- [x] 4.3 真实 CLI 端到端验证：缺键 start 报错、provide 补注入后 validate 通过、键名齐全路径回归
- [x] 4.4 `openspec validate improve-chain-start-ergonomics --strict` 通过
