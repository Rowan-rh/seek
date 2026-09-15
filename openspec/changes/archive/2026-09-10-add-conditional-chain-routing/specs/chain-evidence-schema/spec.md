# Delta: chain-evidence-schema

## ADDED Requirements

### Requirement: 自动跳过步骤不要求 evidence
当 evidenceRequired 步骤因声明式 when 条件不满足而被引擎自动标记为 skipped 时，系统 SHALL 不要求调用方提交 evidence；该步骤 MUST 以 skipped 记录与 skipOutputs 表达“未执行”，不得伪装成 NO_DATA 或 NOT_APPLICABLE 的已执行证据。

#### Scenario: 证据步骤被条件跳过
- **WHEN** evidenceRequired 步骤的 when 条件不满足
- **THEN** 引擎自动跳过且不产生 evidence
- **AND** skipped_steps 明确记录条件和跳过原因
