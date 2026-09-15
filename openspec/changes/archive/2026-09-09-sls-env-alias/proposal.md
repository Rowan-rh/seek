# Proposal: sls-env-alias

## Why

一次真实排查中，用户描述的是"日常环境"，但 `stability-locate` 等应急响应应用的 SLS 配置只有 `prod/pre/yanlian` 三个环境——`--env daily` 直接报 "no SLS config for env 'daily'"。虽然项目配置的 `indexHint` 里写了"yanlian 承载日常"，但 agent 每次都要靠读提示去人工推断映射，很容易查错环境或漏查。`deploy env` 命令早已支持环境同义词自动扩展，SLS 侧却缺位，形成能力不一致。

## What Changes

- **项目级 `envAliases` 配置**：项目配置新增可选字段 `envAliases`（如 `{"daily": "yanlian"}`），声明环境名别名到真实环境的映射。
- **`config.resolve_env()` 别名解析**：新增解析函数；`get_all_sls_configs` 在查环境前先做别名解析，所有下游（`sls query/logs/config`、`trace`、chain 引擎）自动受益。精确匹配优先，仅当请求的环境不存在且别名目标存在时才应用别名。
- **结果标注**：别名生效时，SLS 命令输出附 `resolvedEnv` 字段与提示，避免 agent 误以为查的是字面环境。
- **种子配置落地**：为承载日常流量的 `stability-locate`、`stability-handle`、`stability-agent-master` 预置 `"envAliases": {"daily": "yanlian"}`，用户说"日常"即可直接命中。
- **`sls config` 展示别名**：环境总览输出附 `envAliases`，便于发现。
- **文档同步**：README、command-reference、SKILL.md 说明别名机制与已预置映射。

## Capabilities

### New Capabilities
- `sls-env-alias`: SLS 环境名别名的声明、解析与结果标注规则——`envAliases` 字段语义、精确匹配优先、别名目标必须存在、解析生效时输出可诊断标注。

### Modified Capabilities
（无——本仓库 openspec/specs 下既有 spec 不涉及环境解析）

## Impact

- **代码**：`cli/seek_cli/config.py`（`resolve_env` + `get_all_sls_configs` 接入）、`cli/seek_cli/commands/sls.py`（结果标注与 `sls config` 展示别名）。
- **配置**：`cli/config/projects.json` 与 `cli/seek_cli/resources/config/projects.json`（双镜像同步）为 3 个 yanlian 项目预置 `envAliases`。
- **测试**：新增 `cli/tests/test_env_alias.py`（解析优先级/目标缺失/无配置回退/结果标注）。
- **文档**：`cli/README.md`、`references/command-reference.md`、`SKILL.md`。
- 无外部依赖变化；精确匹配路径行为不变，仅新增别名容错。
