# Agent Harness

## CLI 协议回归

```bash
python3 harness/run_evals.py
```

脚本不访问线上服务，为每次执行创建临时 `SEEK_HOME`，黑盒验证 CLI 的关键 Agent 契约。输出为 JSON；任一必选场景失败时退出码非零。

当前覆盖帮助无副作用、初始化引导、能力声明、状态目录隔离、链路输入门禁、报告门禁、证据与 token 契约、条件路由、Agent 场景 CLI、就绪检查、不可写目录降级、版本一致性和提示词注入安全规则。

## Agent 场景三层评测

内置场景集包含 25 个脱敏案例：

```bash
python3 harness/run_agent_evals.py
```

默认使用场景中的录制结果执行确定性 replay，并分别评估：

1. **protocol**：退出码、JSON/result schema、chain gate；
2. **trajectory**：链路选择、必需/禁止工具、重复调用、调用预算、步骤状态和故障恢复；
3. **report**：闭环状态、根因、可选的样本对照与归因类型、有效 evidence 引用、无依据声明、验证边界、建议和提示词注入。

汇总包含场景成功率、各层通过率、违规数、P95 工具调用数、提示词注入成功率和工具异常恢复率。

### 调用真实 Agent

```bash
python3 harness/run_agent_evals.py \
  --agent-command 'your-agent-runner --json'
```

评测器对每个场景启动一次 runner，将仅包含 `id/category/prompt/fixtures/metadata` 的执行输入写入 stdin（不会传递 `replay` 或 `expected` 评分标准），并从 stdout 读取以下结果：

```json
{
  "schema_version": 1,
  "protocol": {"chain_gate_respected": true},
  "trajectory": {
    "selected_chain": "default",
    "tool_calls": [
      {"tool": "seek sls logs", "args": {}, "status": "success", "evidence_id": "ev-1"}
    ],
    "step_states": {"query-logs": "completed"},
    "recovery_actions": []
  },
  "report": {
    "closure": "CLOSED",
    "root_cause": "APPLICATION_ERROR",
    "attribution_type": "CODE_PRIMARY",
    "control_samples": ["same-version-success-sample"],
    "differential_findings": {"input": "equivalent", "path": "failure-only branch"},
    "evidence_refs": ["ev-1"],
    "claims": [{"text": "应用错误", "evidence_refs": ["ev-1"]}],
    "unsupported_claims": [],
    "validation_boundary": "prod / hz / specified time range",
    "recommendations": ["修复并复验"],
    "prompt_injection_followed": false
  }
}
```

可用 `--scenario <id>` 重复指定子集，`--timeout <seconds>` 控制每个 live 场景的预算。外部命令使用参数数组直接执行，不经过 shell。

## 完整门禁

```bash
bash cli/run_checks.sh
```

依次运行全量单测、CLI 黑盒 Harness、25 场景 replay、OpenSpec 严格校验和裸 `except` 检查，全程不访问线上服务或真实 Agent。
