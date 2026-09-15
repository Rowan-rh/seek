# Design: sls-env-alias

## D1. 配置结构与字段语义

项目配置新增可选顶层字段 `envAliases`：字符串 → 字符串的对象，键为别名，值为 `environments` 中的真实环境名。

```json
{
  "stability-locate": {
    "envAliases": {"daily": "yanlian"},
    "environments": {"prod": {...}, "pre": {...}, "yanlian": {...}}
  }
}
```

- 字段可选；缺失或非法（非对象/值非字符串）时按无别名处理，不阻断配置加载。
- 别名与真实环境重名时精确匹配优先（见 D2）。

## D2. 解析函数 `config.resolve_env(project, env)`

```python
def resolve_env(project, env: str) -> str:
    """解析环境别名，返回用于查配置的环境名。

    优先级：精确匹配 environments > envAliases 映射（目标须存在于 environments）> 原样返回。
    """
    proj = project if isinstance(project, dict) else get_project(project)
    if not proj:
        return env
    environments = proj.get("environments", {})
    if env in environments:
        return env
    aliases = proj.get("envAliases", {})
    if isinstance(aliases, dict):
        target = aliases.get(env)
        if isinstance(target, str) and target in environments:
            return target
    return env
```

- `get_all_sls_configs` 在 `environments.get(env)` 之前先 `env = resolve_env(proj, env)`，使 `get_sls_config`、`sls_client.query_by_config`、`sls config`、trace 等全部下游自动受益，无需逐处改。
- 别名目标不存在于 `environments` 时不应用（返回原 env），避免把请求导向空环境后误判"该环境无日志"。

## D3. 结果标注（防"静默换环境"误导）

`cmd_sls_query` / `cmd_sls_logs`（项目配置模式）与 `cmd_sls_config`（指定 env）：

- 调用 `config.resolve_env(proj, args.env)` 得到 resolved；当 `resolved != args.env` 时：
  - 查询结果附 `resolvedEnv: resolved` 字段；
  - `warnings` 追加 `env '<args.env>' resolved to '<resolved>' via envAliases`；
  - message 中体现实际查询环境。
- `cmd_sls_config`：
  - 指定 env 路径：输出附 `resolvedEnv`（发生解析时）；
  - 全量总览路径：输出附 `env_aliases`（项目配置原值），便于发现映射。
  - env 未命中报错时，data 在 `available_envs` 之外补充 `env_aliases`，提示可用别名。

## D4. 种子配置预置

`cli/config/projects.json` 与 `cli/seek_cli/resources/config/projects.json`（双镜像必须一致）：

- `stability-locate`、`stability-handle`、`stability-agent-master` 三个含 `yanlian` 环境的项目，新增 `"envAliases": {"daily": "yanlian"}`。

## D5. 测试策略（test_env_alias.py）

临时目录替换 `config._BUILTIN_CONFIG`/`config._USER_CONFIG`（沿用 test_hardening.py 模式）：

- 精确匹配优先：env 同时命中 environments 与别名键时不应用别名。
- 别名生效：`daily` → `yanlian` 的 SLS 配置可被 `get_all_sls_configs(p, "daily")` 返回。
- 别名目标缺失：目标不在 environments 时返回原 env，查询结果为空（不误导向）。
- 无 envAliases：行为与现状一致。
- `cmd_sls_config` 指定别名 env：status=ok 且 `resolvedEnv` 标注；未命中 env 报错 data 含 `env_aliases`。
- `cmd_sls_query`/`cmd_sls_logs` 的标注逻辑在纯解析层验证（不触网：mock `sls_client.query_by_config`）。

## D6. 边界与兼容

- `deploy env` 的同义词扩展独立于本机制（A1 pipeline 语义），不改动。
- db conn 的 `--project+--env` bind 反查不走本解析（profile 绑定是精确声明），不改动。
- 既有精确 env 调用路径零行为变化。
