# Delta: harness-readiness

## MODIFIED Requirements

### Requirement: 确定性 Harness 回归入口
仓库 SHALL 提供无需线上凭据和网络访问的 Harness 评测脚本。脚本 MUST 使用临时 `SEEK_HOME`，执行 CLI 黑盒场景并输出 JSON 汇总；任一必选场景失败时 MUST 返回非零退出码。

#### Scenario: 离线评测通过
- **WHEN** 执行 `python3 harness/run_evals.py`
- **THEN** 脚本验证帮助无副作用、capabilities 可解析、seek home 隔离、首步输入门禁、未完成报告拒绝、版本一致性和外部内容安全契约
- **AND** 输出 `status=ok` 及各场景结果
- **AND** 不访问真实 `~/.seek` 或线上服务

#### Scenario: 不可写 seek home 返回结构化错误
- **WHEN** 黑盒场景将 `SEEK_HOME` 指向无法作为目录写入的路径并执行 `seek harness check`
- **THEN** stdout 仍为可解析 JSON
- **AND** 返回 `status=error`、错误码 `HARNESS_NOT_READY`
- **AND** stderr 包含版本标记和错误日志写入失败的降级提示
