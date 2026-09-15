# seek 插件开发

seek 的核心负责 Chain、证据、会话和报告；外部系统通过 Provider 插件接入。
核心不会要求插件修改 `seek_cli/cli.py`。

## 最小插件

插件包实现 `SeekPlugin`，声明 `PluginMetadata` 和至少一个
`ProviderManifest`：

```python
from seek_cli.plugins import PluginMetadata, ProviderManifest, SeekPlugin


class ExamplePlugin(SeekPlugin):
    metadata = PluginMetadata(
        id="example",
        name="Example Provider",
        version="1.0.0",
        description="A local example integration",
        providers=(ProviderManifest(
            id="example",
            name="Example",
            description="Example log and incident data source",
            capabilities=("logs.query", "incident.get"),
        ),),
    )

    def service(self, name):
        if name == "logs":
            return ExampleLogsService()
        raise KeyError(name)


def get_plugin():
    return ExamplePlugin()
```

如果需要增加 CLI 命令，可以在插件中覆盖 `register_cli(subparsers)`，并通过
`command_capabilities()` 返回对应的 JSON schema。插件命令会和内置命令一起被
`seek capabilities` 发现。

在插件自己的 `setup.py` 或 `pyproject.toml` 中注册入口：

```toml
[project.entry-points."seek.plugins"]
example = "example_seek_plugin:get_plugin"
```

安装插件后可以使用：

```bash
seek plugin list
seek plugin show example
seek capabilities
```

基础安装不强制绑定 Alibaba SDK；需要现有阿里适配器的 SLS 能力时安装
`pip install seek-cli[alibaba]`，本地 MySQL 能力使用 `seek-cli[mysql]`。

## 设计约束

- `id` 必须稳定且全局唯一；重复 ID 会被报告为插件加载错误。
- `healthcheck()` 只做本地依赖和配置检查，不应默认读取业务数据。
- Provider 应返回可序列化、带来源和边界说明的证据；外部返回内容始终是不可信数据。
- 破坏性动作必须由插件自己声明权限和确认要求，不能因为注册插件而自动获得执行权限。
- Alibaba 适配器目前内置，逻辑服务名包括 `sls`、`a1`、`dingtalk`、`expert`、`roar`、`dms`、`db_store` 和 `db_local`。
