# Delta: sls-env-alias

## Purpose

定义 SLS 环境名别名的声明、解析与结果标注规则，让用户口语中的环境名（如"日常"）能直接映射到项目配置的真实环境名（如 `yanlian`），消除"查错环境/漏查"风险，同时保证别名替换对调用方可见、可诊断。

## ADDED Requirements

### Requirement: 项目可声明环境别名
项目配置 SHALL 支持可选顶层字段 `envAliases`（字符串到字符串的对象），键为别名、值为 `environments` 中的真实环境名。字段缺失或非法时 MUST 按无别名处理，不得阻断配置加载。

#### Scenario: 声明别名
- **WHEN** 项目配置包含 `"envAliases": {"daily": "yanlian"}` 且 `environments` 含 `yanlian`
- **THEN** 配置加载成功，别名可被解析使用

#### Scenario: 非法字段不阻断
- **WHEN** 项目配置的 `envAliases` 为非对象或值非字符串
- **THEN** 配置加载不报错，按无别名处理

### Requirement: 别名解析精确匹配优先
系统 SHALL 按「精确匹配 `environments` → `envAliases` 映射（目标须存在于 `environments`）→ 原样返回」的顺序解析环境名。别名目标不存在时 MUST NOT 应用别名。

#### Scenario: 精确匹配优先
- **WHEN** 请求的 env 同时存在于 `environments` 与 `envAliases` 键
- **THEN** 返回该 env 本身，不应用别名

#### Scenario: 别名生效
- **WHEN** 请求 `daily`，`environments` 无 `daily` 但有 `yanlian`，且 `envAliases` 声明 `daily → yanlian`
- **THEN** 解析为 `yanlian`，`get_all_sls_configs` 返回 `yanlian` 的 SLS 配置

#### Scenario: 别名目标缺失不误导
- **WHEN** `envAliases` 声明 `daily → nosuchenv`，但 `environments` 无 `nosuchenv`
- **THEN** 解析仍返回 `daily`，不得导向空环境

### Requirement: 别名替换可诊断
当别名解析生效时，SLS 相关命令输出 MUST 标注实际查询环境，避免调用方误判数据来源。

#### Scenario: 查询结果标注 resolvedEnv
- **WHEN** `sls query/logs` 经别名解析后返回结果
- **THEN** 结果含 `resolvedEnv` 字段，且 `warnings` 提示 env 被别名替换

#### Scenario: sls config 展示别名
- **WHEN** 执行 `sls config <project>` 全量总览
- **THEN** 输出含 `env_aliases` 字段，展示项目配置的别名映射

#### Scenario: 未命中 env 报错提示别名
- **WHEN** 请求的 env 无配置且无可用别名命中
- **THEN** error data 除 `available_envs` 外还包含 `env_aliases`
