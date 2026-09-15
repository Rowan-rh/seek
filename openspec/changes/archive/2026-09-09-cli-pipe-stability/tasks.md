# Tasks: cli-pipe-stability

## 1. 解析错误 JSON 化（cli/seek_cli/cli.py）

- [x] 1.1 定义 `_JsonArgumentParser(argparse.ArgumentParser)`，重写 `error()`：usage → stderr，标准 error JSON（`ARGPARSE_ERROR`）→ stdout，`sys.exit(2)`
- [x] 1.2 `_build_parser()` 根 parser 改用 `_JsonArgumentParser`（子命令经 `add_subparsers` 默认 parser_class 自动继承）

## 2. `--limit` 别名（cli/seek_cli/cli.py）

- [x] 2.1 `sls query`、`sls logs`、`trace query`、`db query` 的 `--max` 追加 `--limit` 次选项字符串，显式 `dest="max"`，help 标注别名

## 3. 测试

- [x] 3.1 新建 `cli/tests/test_pipe_stability.py`：解析错误 stdout JSON/退出码 2/stderr usage、缺参路径、`--limit`↔`--max` 等价解析
- [x] 3.2 `python -m unittest discover cli/tests` 全绿（含 capabilities 契约测试）

## 4. 文档与验证

- [x] 4.1 `cli/README.md`、`references/command-reference.md`：标注 `--limit`/`--max` 别名与"stdout 恒为 JSON、非零即错"管道契约
- [x] 4.2 真实 CLI 端到端：非法参数确认 stdout 为合法 JSON 且退出码非零；`--limit` 生效
- [x] 4.3 `openspec validate cli-pipe-stability --strict` 通过
