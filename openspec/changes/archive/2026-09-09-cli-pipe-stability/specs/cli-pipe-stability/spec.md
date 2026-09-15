# Delta: cli-pipe-stability

## Purpose

定义 CLI 输出契约在管道编排场景下的稳定性要求：任何调用路径（含参数解析失败）stdout 都必须输出可解析的结构化 JSON，且条数上限参数提供 `--limit`/`--max` 双写兼容，避免 agent 因参数习惯差异或解析错误导致管道中断。

## ADDED Requirements

### Requirement: 参数解析失败仍输出结构化 JSON
系统 SHALL 在 argparse 参数解析失败时，将 usage 输出到 stderr，同时向 stdout 打印符合统一输出契约的 error JSON（`status=error`、`code=ARGPARSE_ERROR`），并以非零退出码结束。该行为 MUST 覆盖根命令、子命令及嵌套子命令（含 `db conn` 下各子命令）。

#### Scenario: 非法选项输出 JSON 到 stdout
- **WHEN** 执行 `seek sls query --bogus-flag`
- **THEN** stdout 为合法 JSON，`status=error` 且 `error.code=ARGPARSE_ERROR`
- **AND** stderr 包含 usage
- **AND** 进程退出码非零

#### Scenario: 缺失必填参数输出 JSON
- **WHEN** 执行 `seek sls query`（缺 `--env`/`--query`）导致 argparse 报 required 错误
- **THEN** stdout 为合法 JSON，`error.code=ARGPARSE_ERROR`，退出码非零

#### Scenario: 嵌套子命令同样生效
- **WHEN** 执行 `seek db conn`（缺必需子命令）或 `seek db conn add`（缺必填项）
- **THEN** stdout 为合法 JSON，`error.code=ARGPARSE_ERROR`

#### Scenario: --help 行为不变
- **WHEN** 执行 `seek sls query --help`
- **THEN** stdout 打印帮助文本并以退出码 0 结束（不进入 ARGPARSE_ERROR 路径）

### Requirement: 条数上限参数 --limit 与 --max 等价
对于以 `--max` 表示条数上限的命令（`sls query`、`sls logs`、`trace query`、`db query`），系统 SHALL 同时接受 `--limit` 作为等价别名，两者映射到同一内部参数。

#### Scenario: --limit 与 --max 解析等价
- **WHEN** 分别执行 `seek sls query p --env daily --query q --limit 50` 与 `... --max 50`
- **THEN** 两者解析出的条数上限值相同（均为 50）

#### Scenario: 原生命名不受影响
- **WHEN** 执行 `seek chain sessions --limit 10`
- **THEN** 行为与本变更前一致（`--limit` 为其原生命名）
