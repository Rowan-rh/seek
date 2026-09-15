# Proposal: add-db-local-direct-connect

## Why

`seek db` 目前只有 DMS MCP 一条查询通路（经 `~/.qoderwork/mcp.json` 启动 MCP 子进程、用 `database_id` 走 DMS 网关执行 SQL）。生产受管实例适用，但日常/预发环境的库大多数场景是「本地方本地直连」：网络可达、无 DMS 纳管或无 DMS 权限、且直连延迟远低于 DMS 网关。当前 agent 遇到日常环境 DB 取证需求时没有可用命令，只能退化为手工操作。

## What Changes

- 新增**本地直连 backend**：`seek_cli/integrations/db_local.py`，基于 PyMySQL 直连 MySQL（一期仅 MySQL，驱动层留薄抽象供后续扩展 PostgreSQL）。
- 新增**连接 profile 管理**命令：`seek db conn add/list/test/remove`，profile 存储在 `~/.seek/config/db.json`（权限 0600，fcntl 锁 + tempfile 原子写，与 seek.json 一致）。
- 扩展 `seek db query/tables/schema` 的目标寻址：`--conn <profile>` 直连、`--project <p> --env <e>` 按 profile 的 `bind` 字段反查、原有位置参数 `<database_id>` 走 DMS 路径保持不变（向后兼容）。
- 密码支持 `env:VAR_NAME` 环境变量引用（推荐）或明文落盘（文件强制 0600，`conn list` 输出脱敏）。
- 安全约束：复用现有只读 SQL 校验（单条 SELECT/WITH/EXPLAIN）；`bind.env` 为生产类（prod/online/publish*）的 profile 默认拒绝直连，须显式 `--i-know-this-is-prod`；结果行数上限默认 500（`--max`，上限 5000），超限截断并标记 `truncated`。
- 输出格式与 DMS 路径对齐（columns + rows），agent 无需区分 backend 解析结果。
- capabilities 注册新命令；doctor 增加 db.json 结构校验与连通性检查。

## Capabilities

### New Capabilities
- `db-local-connections`: 本地直连数据库的连接 profile 管理、目标寻址（--conn / --project+--env / DMS 回退）、安全约束（只读校验、生产环境熔断、行数上限）与输出格式规则。

### Modified Capabilities
（无——openspec/specs 下现有 chain-report-templates 与本变更无交集）

## Impact

- **代码**：新增 `cli/seek_cli/integrations/db_local.py`；扩展 `cli/seek_cli/commands/db.py`（backend 分发 + conn 子命令）；`cli/seek_cli/cli.py`（参数注册）；`cli/seek_cli/commands/capabilities.py`（能力注册）；`cli/seek_cli/commands/doctor.py`（连通性检查）。
- **配置**：新增 `~/.seek/config/db.json`（运行时生成，不入库）。
- **依赖**：`cli/setup.py` 增加 optional extra `mysql`（PyMySQL），import 失败时给安装指引而非裸 ImportError。
- **测试**：新增 `cli/tests/test_db_local.py`（profile 读写/脱敏、只读校验复用、环境熔断、行数截断、寻址优先级）。
- **文档**：`SKILL.md`、`cli/README.md`、`references/command-reference.md` 补充「日常优先本地直连、生产走 DMS」路由指引。
- 现有 DMS 路径命令签名不变，纯新增。
