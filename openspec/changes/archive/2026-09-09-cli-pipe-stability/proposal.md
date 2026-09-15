# Proposal: cli-pipe-stability

## Why

一次真实排查中，agent 把 seek 输出接进 `python3 -c "json.load(sys.stdin)"` 做管道解析，遇到两类问题直接炸掉：

1. **argparse 解析失败时 stdout 为空**。命令参数写错（如 `sls query` 误用 `--limit`）时，argparse 把 usage/错误打到 stderr 并 `SystemExit(2)`，stdout 没有任何 JSON——管道下游 `json.load` 直接 EOF 报错。业务错误已有 JSON，唯独参数错误这条路径绕过了统一输出契约。
2. **`--limit` 与 `--max` 命名不一致**。条数上限参数在不同命令里叫法不一：`sls query/logs`、`trace query`、`db query` 用 `--max`，而 `chain sessions`、`dingtalk`、`errors list` 用 `--limit`。agent 凭习惯写 `--limit` 就报 unrecognized arguments，且错误信息混进管道导致误判。

## What Changes

- **参数解析错误也走统一 JSON 输出**：自定义 `ArgumentParser` 子类重写 `error()`，usage 仍打 stderr（供人阅读），同时向 stdout 打印标准 error JSON（`code=ARGPARSE_ERROR`），进程退出码保持非零。保证 stdout 恒为可解析 JSON。
- **`--limit` 作为 `--max` 的别名**：为所有以 `--max` 表示条数上限的命令（`sls query`、`sls logs`、`trace query`、`db query`）追加 `--limit` 选项字符串，映射到同一 dest，两种写法均可。
- **文档同步**：cli/README.md、references/command-reference.md 标注别名与"stdout 恒为 JSON"约定。

## Capabilities

### New Capabilities
- `cli-pipe-stability`: CLI 输出契约面向管道编排的稳定性——参数解析失败时 stdout 仍输出结构化 JSON、条数上限参数 `--limit`/`--max` 双写兼容。

### Modified Capabilities
（无）

## Impact

- **代码**：`cli/seek_cli/cli.py`（自定义 parser 子类 + error 重写；4 处 `--max` 命令追加 `--limit` 别名）。
- **测试**：新增 `cli/tests/test_pipe_stability.py`（解析错误 stdout JSON、别名映射、退出码）；capabilities 契约测试不受影响（别名用次选项字符串，`option_strings[0]` 仍为 `--max`）。
- **文档**：`cli/README.md`、`references/command-reference.md`。
- 无外部依赖变化；既有合法调用行为不变，仅新增容错路径。
