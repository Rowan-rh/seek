# db-local-connections Specification

## Purpose
定义 seek CLI 本地直连数据库的连接 profile 管理、目标寻址与安全约束规则，使日常/预发环境可通过本机直连完成 DB 取证，同时保持生产路径（DMS）与既有命令签名不变。

## Requirements

### Requirement: 连接 profile 管理
系统 SHALL 提供 `seek db conn add/list/test/remove` 命令管理本地连接 profile。profile 存储在 `~/.seek/config/db.json`，MUST 以 0600 权限写入，写入 MUST 使用文件锁 + 原子替换（与 seek.json 一致）。

#### Scenario: 添加含环境变量密码的 profile
- **WHEN** 执行 `seek db conn add <name> --type mysql --host H --port P --database D --user U --password env:VAR --project P --env daily`
- **THEN** db.json 中新增该 profile，password 字段以 `env:VAR` 原样存储
- **AND** 文件权限为 0600

#### Scenario: list 输出密码脱敏
- **WHEN** 执行 `seek db conn list`
- **THEN** 每个 profile 输出 name/type/host/port/database/user/bind 字段
- **AND** password 字段脱敏展示（明文密码不原样输出）

#### Scenario: test 执行连通性检查
- **WHEN** 执行 `seek db conn test <name>`
- **THEN** 建立真实连接并执行 `SELECT 1`，成功返回 ok 状态，失败返回含原因的错误（code=DB_CONNECT_ERROR）

#### Scenario: 缺少驱动时给出安装指引
- **WHEN** 未安装 PyMySQL 时执行任何本地直连操作
- **THEN** 返回明确的安装指引错误（如 `pip install seek-cli[mysql]`），不抛裸 ImportError 堆栈

### Requirement: 目标寻址与 backend 分发
`seek db query/tables/schema` SHALL 支持三种目标寻址方式，优先级从高到低：`--conn <profile>` > `--project + --env`（按 profile 的 bind 字段反查）> 位置参数（DMS database_id，现有行为不变）。

#### Scenario: --conn 走本地直连
- **WHEN** 执行 `seek db query --conn <name> --sql "SELECT ..."`
- **THEN** 通过本地直连执行查询，不启动 DMS MCP 子进程

#### Scenario: --project + --env 反查 profile
- **WHEN** 执行 `seek db query --project qt-stability --env daily --sql "..."` 且存在 bind 为该项目+环境的唯一 profile
- **THEN** 自动选用该 profile 执行查询

#### Scenario: bind 反查无匹配或多匹配报错
- **WHEN** `--project + --env` 反查到 0 个或多个 profile
- **THEN** 返回错误并提示可用 profile 列表或改用 --conn 显式指定

#### Scenario: DMS 路径向后兼容
- **WHEN** 执行 `seek db query <database_id> --sql "..."`（不带 --conn/--project）
- **THEN** 行为与本变更前完全一致（走 DMS MCP executeScript）

### Requirement: 只读 SQL 校验复用
本地直连路径 SHALL 复用 DMS 路径相同的只读 SQL 校验规则：仅允许单条 SELECT/WITH/EXPLAIN，拒绝 DML/DDL/事务控制/多语句/可执行注释，以及全部锁定读语法（FOR UPDATE、FOR SHARE、LOCK IN SHARE MODE）。

#### Scenario: 非只读 SQL 被拒绝
- **WHEN** 通过 --conn 执行 `UPDATE ...` 或多语句 SQL
- **THEN** 返回 READ_ONLY_SQL_REQUIRED 错误，且不建立数据连接

#### Scenario: 锁定读被拒绝
- **WHEN** 通过 --conn 执行 `SELECT * FROM t LOCK IN SHARE MODE`、`SELECT * FROM t FOR SHARE` 或 `SELECT * FROM t FOR UPDATE OF t`
- **THEN** 返回 READ_ONLY_SQL_REQUIRED 错误，且不建立数据连接

### Requirement: 生产环境熔断
bind.env 为生产类环境（prod/online 或 publish* 前缀）的 profile SHALL 默认拒绝直连查询，仅在显式传入 `--i-know-this-is-prod` 时放行。

#### Scenario: 生产 profile 默认拒绝
- **WHEN** 对一个 bind.env 为 prod 的 profile 执行查询且未传 `--i-know-this-is-prod`
- **THEN** 返回错误提示该 profile 绑定生产环境，直连需显式确认参数

#### Scenario: 显式确认后放行
- **WHEN** 对同一 profile 传入 `--i-know-this-is-prod`
- **THEN** 正常执行查询

### Requirement: 结果行数上限
本地直连查询 SHALL 限制返回行数：默认 500 行，可通过 `--max` 调整，上限 5000；超限时结果截断并标记 `truncated: true`。

#### Scenario: 超限截断
- **WHEN** 查询结果行数超过 max_rows
- **THEN** 仅返回前 max_rows 行，输出含 `truncated: true` 与实际返回行数

### Requirement: 输出格式统一
本地直连查询的输出 SHALL 与 DMS 路径语义对齐，包含列名与行数据（columns + rows），agent 无需按 backend 区分解析逻辑。

#### Scenario: 查询输出结构
- **WHEN** 本地直连查询成功
- **THEN** data 包含 `columns`（列名数组）、`rows`（行数组）、`rowCount`，外层为统一 success 结构
