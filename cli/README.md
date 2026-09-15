# seek CLI

这是 `seek` 的 Python 包和命令行入口。它提供通用排查编排能力，不绑定任何云厂商或告警平台。

## 安装

```bash
python3 -m pip install -e .
seek --help
```

## 命令

```text
seek capabilities                         # 输出机器可读能力清单
seek plugin list|show <name>              # 查看已安装插件
seek project list|show|add                # 管理通用项目目录
seek chain list|show|start|step|complete  # 管理排查链路与会话
seek chain context|validate|report        # 查看上下文、校验和生成报告
seek config show|get|set|unset|path       # 管理核心配置
seek perf report|clear                    # 查看命令性能日志
seek harness check|evaluate               # 检查或评估 Agent Harness
seek errors list|clear                    # 查看或清理错误记录
```

所有命令默认向 stdout 输出 JSON；错误通过非零退出码表达。`capabilities` 是推荐的 Agent 发现入口。

## 插件机制

核心通过 Python entry point group `seek.plugins` 发现插件。插件负责自己的 Provider、凭据、外部 SDK 和命令；核心只消费插件声明的能力，不内置平台适配器。

```toml
[project.entry-points."seek.plugins"]
example = "example_seek_plugin:plugin"
```

详见仓库根目录 [`PLUGIN.md`](../PLUGIN.md)。

## 本地开发

```bash
python3 -m pytest -q
./run_checks.sh
```

测试使用临时 `SEEK_HOME`，不会读取或改写用户的真实配置。
