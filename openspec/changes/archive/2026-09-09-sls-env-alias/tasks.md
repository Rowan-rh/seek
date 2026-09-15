# Tasks: sls-env-alias

## 1. 配置解析（cli/seek_cli/config.py）

- [x] 1.1 新增 `resolve_env(project, env)`：精确匹配优先 → envAliases 映射（目标须存在）→ 原样返回
- [x] 1.2 `get_all_sls_configs` 查环境前接入 `resolve_env`（下游 get_sls_config/query_by_config/sls config/trace 自动受益）

## 2. 结果标注（cli/seek_cli/commands/sls.py）

- [x] 2.1 `cmd_sls_query`/`cmd_sls_logs` 项目配置模式：别名生效时输出 `resolvedEnv` + warnings 提示
- [x] 2.2 `cmd_sls_config`：指定 env 时输出 `resolvedEnv`；全量总览输出 `env_aliases`；未命中报错 data 补 `env_aliases`

## 3. 种子配置

- [x] 3.1 `cli/config/projects.json` 与 `cli/seek_cli/resources/config/projects.json`：stability-locate / stability-handle / stability-agent-master 预置 `"envAliases": {"daily": "yanlian"}`（双镜像一致）

## 4. 测试

- [x] 4.1 新建 `cli/tests/test_env_alias.py`：精确优先/别名生效/目标缺失/无配置回退/config 标注与报错 data
- [x] 4.2 `python -m unittest discover cli/tests` 全绿

## 5. 文档与验证

- [x] 5.1 `cli/README.md`、`references/command-reference.md`、`SKILL.md`：别名机制与已预置映射说明
- [x] 5.2 真实 CLI 验证：`sls config stability-locate --env daily` 命中 yanlian 且带 resolvedEnv 标注
- [x] 5.3 `openspec validate sls-env-alias --strict` 通过
