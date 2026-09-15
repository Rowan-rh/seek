## MODIFIED Requirements

### Requirement: 确定性 Harness 回归入口
仓库 SHALL 提供无需线上凭据和网络访问的 Harness 评测脚本。脚本 MUST 使用临时 `SEEK_HOME`，执行 CLI 黑盒场景和内置 Agent 场景 replay，并输出 JSON 汇总；任一必选场景失败时 MUST 返回非零退出码。

#### Scenario: 离线评测通过
- **WHEN** 执行 `bash cli/run_checks.sh`
- **THEN** 脚本验证 CLI 黑盒契约并执行内置 Agent 场景 replay
- **AND** Agent 场景报告包含 protocol、trajectory、report 三层结果和聚合指标
- **AND** 全过程不访问真实 `~/.seek`、线上服务或真实 Agent

#### Scenario: 不可写 seek home 返回结构化错误
- **WHEN** 黑盒场景将 `SEEK_HOME` 指向无法作为目录写入的路径并执行 `seek harness check`
- **THEN** stdout 仍为可解析 JSON
- **AND** 返回 `status=error`、错误码 `HARNESS_NOT_READY`
- **AND** stderr 包含版本标记和错误日志写入失败的降级提示
