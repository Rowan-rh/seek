# chain-evidence-schema Specification

## Purpose
为执行外部查询或代码取证的链路步骤定义结构化证据契约，使无数据、不适用和工具错误不会与未执行查询混淆。

## Requirements

### Requirement: 证据型步骤必须提交合法 evidence
声明 `evidenceRequired: true` 的步骤在 complete 时 SHALL 要求 evidence 对象。evidence MUST 包含合法 status 和非空 boundary；FOUND/NO_DATA MUST 至少包含一个带非空 tool/reference 的 source；NO_DATA/NOT_APPLICABLE/TOOL_ERROR MUST 包含非空 reason。

#### Scenario: 查询成功并找到证据
- **WHEN** evidence status 为 FOUND，sources 至少有一项且 boundary 非空
- **THEN** 步骤可以完成，evidence 随步骤持久化

#### Scenario: 空 outputs 没有证据说明
- **WHEN** evidenceRequired 步骤只提交声明 outputs，没有提交 evidence
- **THEN** complete 返回 EVIDENCE_REQUIRED 且步骤不推进

#### Scenario: 查询无结果但边界完整
- **WHEN** status 为 NO_DATA，包含查询 source、reason 和 boundary
- **THEN** 步骤可以完成，且 NO_DATA 不被转换成 FOUND

#### Scenario: 升级前会话保持可继续
- **WHEN** 持久化 session 不含 `evidence_contract_version`
- **THEN** 继续按旧契约完成步骤，不强制补交 evidence

### Requirement: 更正保留证据历史
更正 evidenceRequired 步骤 outputs 时 SHALL 提交合法 evidence。新 evidence MUST 写入 amendment，并更新 session 的 step_evidence 当前视图；原 completed step evidence MUST 保留。

#### Scenario: 证据更正
- **WHEN** completed 步骤通过 amend 提交新 outputs 和 evidence
- **THEN** 原完成记录不变，amendments 包含新 evidence，step_evidence 指向最新证据

### Requirement: 自动跳过步骤不要求 evidence
当 evidenceRequired 步骤因声明式 when 条件不满足而被引擎自动标记为 skipped 时，系统 SHALL 不要求调用方提交 evidence；该步骤 MUST 以 skipped 记录与 skipOutputs 表达“未执行”，不得伪装成 NO_DATA 或 NOT_APPLICABLE 的已执行证据。

#### Scenario: 证据步骤被条件跳过
- **WHEN** evidenceRequired 步骤的 when 条件不满足
- **THEN** 引擎自动跳过且不产生 evidence
- **AND** skipped_steps 明确记录条件和跳过原因
