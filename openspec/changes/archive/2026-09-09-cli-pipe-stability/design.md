# Design: cli-pipe-stability

## D1. 参数解析错误输出 JSON（stdout 恒可解析）

现状：`main()` 中 `parser.parse_args()` 在 try 块之外。argparse 遇非法参数时调用 `parser.error(message)`，默认实现把 usage 打到 stderr 并 `sys.exit(2)`，stdout 为空 → 管道下游 `json.load` EOF 崩溃。

方案：在 `cli.py` 定义 `_JsonArgumentParser(argparse.ArgumentParser)`，重写 `error()`：

```python
class _JsonArgumentParser(argparse.ArgumentParser):
    """参数解析失败时：usage 走 stderr，JSON 错误走 stdout，退出码非零。"""
    def error(self, message):
        self.print_usage(sys.stderr)
        result = error(f"argument error: {message}", code="ARGPARSE_ERROR",
                       data={"hint": "run with --help to see valid arguments"})
        print_result(result, fmt="json")   # stdout
        sys.exit(2)
```

`_build_parser()` 的根 parser 改用 `_JsonArgumentParser`。argparse 的 `add_subparsers` 默认 `parser_class=type(self)`，因此全部子命令/嵌套子命令（含 `db conn`）自动继承该行为，无需逐处改。

- 退出码保留 argparse 语义 `2`（区别于业务错误 `1`），但 stdout 恒为合法 JSON、退出码非零，满足管道编排"非零即错、stdout 可解析"契约。
- `--help` 不经过 `error()`，仍正常打印并以 0 退出，行为不变。
- 不写 error_log：parse 失败发生在命令分发前，且避免沙箱/测试环境写 `~/.seek` 失败干扰。

## D2. `--limit` 作为 `--max` 别名

在 4 处以 `--max` 表示条数上限的命令追加次选项字符串：

| 命令 | 现状 | 改后 |
|------|------|------|
| `sls query` | `--max` | `add_argument("--max", "--limit", dest="max", ...)` |
| `sls logs` | `--max` | 同上 |
| `trace query` | `--max` | 同上 |
| `db query` | `--max` | 同上 |

- argparse 的 `option_strings` 按传入顺序保存，`option_strings[0]` 仍为 `--max`，capabilities 契约测试（取 `option_strings[0]`）与 capabilities.py 声明（`--max`）均不受影响。
- 两写法映射同一 `dest="max"`，命令实现零改动。
- 显式写 `dest="max"`，避免 argparse 依首选项推导 dest 时的歧义。
- help 文案标注 `(别名 --limit)`。

`--limit` 已是 `chain sessions`/`dingtalk`/`errors list` 的原生命名，这些不动。

## D3. 测试策略

- `test_pipe_stability.py`：
  - 非法参数 → 捕获 stdout 为合法 JSON、`status=error`、`code=ARGPARSE_ERROR`、退出码 2；stderr 含 usage。
  - 缺必填子命令/参数 → 同样输出 JSON。
  - `sls query --limit N` 与 `--max N` 解析到同一 `args.max`；`db query --limit` 同理。
- capabilities 契约测试回归全绿。

## D4. 兼容性与边界

- 既有合法调用行为完全不变；仅新增容错（解析错误 JSON 化）与兼容（别名）。
- `error()` 内 `print_result` 使用与业务路径一致的 JSON 序列化（`ensure_ascii=False, indent=2`），管道可直接 `json.load`。
