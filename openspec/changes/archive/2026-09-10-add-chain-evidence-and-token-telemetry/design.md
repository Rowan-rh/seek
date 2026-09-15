# Design: add-chain-evidence-and-token-telemetry

## Context

链路引擎已有 requiredInputs/outputs 的字段级门禁和可靠持久化，但 outputs 内容仍是自由 JSON。内置链路中的查询步骤需要一种紧凑、可机器检查的证据元数据，同时允许无数据、分支不适用和工具失败成为合法但可区分的结果。Token 信息由调用 Agent/Harness 提供，CLI 不尝试估算。

## Goals / Non-Goals

**Goals:**
- 防止证据步骤仅提交空 outputs 后无说明地推进；
- 保留查询坐标和验证边界，方便报告与评测；
- 按步骤和 session 汇总 token 消耗；
- 保持自定义旧链路兼容。

**Non-Goals:**
- 不验证证据内容真伪；
- 不自动读取模型供应商账单；
- 不把 token 数量计入任何质量分数或 ready 判定；
- 不在本变更实现条件分支。

## Decisions

### D1. evidence 作为步骤元数据而非普通 output

`--evidence` 接受独立 JSON 对象，避免与领域 outputs 命名冲突。结构为：

```json
{
  "status": "FOUND|NO_DATA|NOT_APPLICABLE|TOOL_ERROR",
  "sources": [{"tool": "seek sls query", "reference": "query/time/target"}],
  "boundary": "已检查的环境、时间窗和未覆盖范围",
  "reason": "非 FOUND 状态的原因"
}
```

`FOUND` 和 `NO_DATA` 要求至少一个 source；全部状态要求非空 boundary；非 FOUND 状态要求 reason。

### D2. 通过 evidenceRequired 渐进启用

只有步骤声明 `evidenceRequired: true` 且 session 含 `evidence_contract_version: 1` 时 complete/amend 强制 evidence。新 session 自动写入该版本；升级前已落盘 session 因缺少版本字段继续按旧契约执行。内置链路中实际调用外部查询或源码检索的步骤启用；纯分支判断、汇总和报告步骤不启用。用户自定义旧链路不受影响。

### D3. token usage 是纯观测字段

`--token-usage` 接受 `input_tokens`、`output_tokens`、`cached_input_tokens`、`reasoning_tokens`，均为可选非负整数，拒绝未知字段。它随 completed step 保存，由 `chain usage` 汇总，不参与 validate、complete 成功条件、Harness ready 或最终评分。

### D4. 更正记录可以携带新证据

`chain amend --evidence` 在修改 evidenceRequired 步骤 outputs 时同样要求合法 evidence，并把更正证据追加到 amendment，随后更新 `step_evidence` 当前视图，保留原完成记录。

## Risks / Trade-offs

- 内置链路调用方需要同步传递 evidence → SKILL、命令参考和错误提示提供迁移示例。
- Agent 可以伪造结构合法的证据 → 本层只提供可审计结构，真实性由后续场景评测或来源签名解决。
- token 由调用方上报，准确性依赖 Harness → 输出明确标注 `reported`，不用于评分。
