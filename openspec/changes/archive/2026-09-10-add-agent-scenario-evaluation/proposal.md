# Proposal: add-agent-scenario-evaluation

## Why

现有 `harness/run_evals.py` 主要验证 CLI 协议和本地门禁，不能判断 Agent 是否选择正确链路、是否产生冗余工具调用、是否在工具故障后恢复，以及最终报告是否由有效证据支撑。

## What Changes

- 新增版本化场景集和稳定的 Agent runner 输入/输出协议。
- 建立协议、轨迹、最终报告三层确定性评分，输出稳定违规码和聚合指标。
- 支持内置 replay 模式用于离线 CI，也支持外部命令 runner 实际调用 Agent。
- 首批加入 24 个脱敏案例，覆盖成功、无数据、环境/Region 错误、超时、限流、非法 JSON、部分结果、证据冲突、提示词注入和无法闭环。
- 将 Agent 场景 replay 纳入 `cli/run_checks.sh`，并提供独立 JSON 报告入口。

## Capabilities

### New Capabilities
- `agent-scenario-evaluation`: 定义场景格式、Agent runner 协议、三层评测、违规码与汇总指标。

### Modified Capabilities
- `harness-readiness`: 仓库级离线门禁增加 Agent 场景 replay 评测，但仍不访问网络或真实账号。

## Impact

影响 Harness 脚本、CLI Harness 能力声明、测试入口、文档和 CI 本地门禁。外部 Agent 通过子进程 JSON 协议接入，不新增 Python 第三方依赖。
