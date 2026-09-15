# Delta: skill-install-consistency

## MODIFIED Requirements

### Requirement: 版本声明一致性校验
系统 SHALL 在 `seek skill update` 与 `seek skill status` 中，将源码 `SKILL.md` frontmatter 的 `cli_version_ref` 与实际运行的 CLI 版本（`seek_cli.__version__`，与 `seek version` 同源）比较，并在输出 data 顶层给出 `version_consistency` 结构，含 `declared_cli_version`、`actual_cli_version` 与三态 `consistent`（`true` 一致 / `false` 漂移 / `null` 未声明）。版本漂移是运行时告警而非失败：命令 MUST 保持 `status=ok` 与退出码 0，但 MUST 在 message 中追加不匹配告警。仓库测试和 PR 检查 MUST 将源码树中的版本漂移视为失败，阻止不一致版本合入。

#### Scenario: 声明与实际不一致时如实告警
- **WHEN** `SKILL.md` 声明 `cli_version_ref: 0.5.0` 而实际 `__version__` 为 `0.4.0`，执行 `seek skill update`
- **THEN** 输出 `status=ok`、退出码 0
- **AND** `data.version_consistency.consistent` 为 `false`
- **AND** message 包含“版本声明不匹配”类告警文本

#### Scenario: 一致时静默
- **WHEN** `cli_version_ref` 与实际 `__version__` 相同，执行 `seek skill update`
- **THEN** `data.version_consistency.consistent` 为 `true`，message 不含不匹配告警

#### Scenario: 未声明时不告警
- **WHEN** frontmatter 无 `cli_version_ref` 字段
- **THEN** `consistent` 为 `null`，不产生告警

#### Scenario: 仓库版本漂移被门禁阻断
- **WHEN** 源码树中的 `SKILL.md#cli_version_ref` 与 `seek_cli.__version__` 不一致
- **THEN** 文档一致性测试或 PR 检查失败
- **AND** 失败信息同时给出声明版本与实际版本
