# Design: add-db-local-direct-connect

## D1. 总体架构：双 backend 分发

`seek db` 命令层引入 backend 分发，DMS 路径保持原样：

```
seek db query/tables/schema
        │
        ├─ --conn <profile>          → LocalDbClient（db_local.py）
        ├─ --project X --env Y       → bind 反查唯一 profile → LocalDbClient
        └─ 位置参数 <database_id>     → dms_client（现有路径，不动）
```

分发逻辑集中在 `commands/db.py` 的 `_resolve_local_profile(args)`：返回 profile 则走本地，返回 None 则走 DMS。DMS 分支代码零改动，保证向后兼容。

## D2. 连接 profile 存储：~/.seek/config/db.json

遵循「配置凭证集中存储在 ~/.seek/」规范。不复用 seek.json 的原因：连接是多实例结构化数据（dict of profiles），与 seek.json 的点路径 KEY_SCHEMA 白名单模式不匹配；独立文件也便于 0600 权限单独控制。

```json
{
  "connections": {
    "qt-stability-daily": {
      "type": "mysql",
      "host": "10.x.x.x",
      "port": 3306,
      "database": "qt_stability",
      "user": "qt_read",
      "password": "env:QT_STABILITY_DB_PWD",
      "bind": { "project": "qt-stability", "env": "daily" }
    }
  }
}
```

- 写入：fcntl 锁 + tempfile 原子替换 + `os.chmod(0o600)`，模式照搬 `settings.py` 的 `_save_settings/_settings_lock`。
- 密码：`env:VAR` 前缀表示运行时读环境变量（推荐，agent 场景凭证走 shell 环境）；也允许明文（文件已 0600）。`conn list` 一律脱敏（复用 `settings.mask_secret`）。
- `bind` 可选；反查时按 (project, env) 精确匹配，唯一命中才生效，0 个或多个命中报错并列出候选 profile 名。

## D3. 驱动选型：PyMySQL optional extra

- 选型理由：纯 Python 免编译（macOS/Linux 直接 pip 安装）；游标 API 简单，列名 + 行数据直接映射目标输出格式。
- 备选否决：subprocess 包装 `mysql` CLI —— 输出解析脆弱（表格/TSV 转义）、依赖客户端安装、无法可靠拿到列类型；SQLAlchemy —— 对单驱动场景过重。
- 集成方式：`setup.py` 增加 `extras_require={"mysql": ["PyMySQL>=1.1"]}`；`db_local.py` 内部延迟 import，失败时抛带安装指引的 RuntimeError（`pip install seek-cli[mysql]` 或 `pip install pymysql`），由命令层转成 error 输出，不产生裸 ImportError 堆栈。
- 一期仅 MySQL；`LocalDbClient` 按 `type` 字段分支，后续加 PostgreSQL 只需新增驱动分支。

## D4. LocalDbClient 接口

```python
class LocalDbClient:
    def __init__(self, profile: dict): ...        # 解析 env: 密码
    def test(self) -> dict                        # SELECT 1
    def list_tables(self) -> list[str]            # SHOW TABLES
    def table_schema(self, table: str) -> dict    # SHOW CREATE TABLE + information_schema.columns
    def query(self, sql: str, max_rows: int) -> dict
    def close(self) -> None
```

连接参数硬约束：`connect_timeout=5`、`read_timeout=30`、`charset=utf8mb4`、`autocommit=True`。
行数限制实现：`fetchmany(max_rows + 1)`，多取 1 行用于判断 truncated，不 fetchall 全量拉取。
生命周期：每次命令新建连接、用完即关（CLI 短生命周期，不做连接池）。

## D5. 安全约束

1. **只读校验复用**：本地路径调用 `db.py` 现有 `_validate_read_only_sql()`（校验在建连之前执行，非法 SQL 不触达数据库）。
2. **生产熔断**：`bind.env` 命中 `prod`/`online` 或 `publish` 前缀时，未传 `--i-know-this-is-prod` 直接拒绝（error code=PROD_DIRECT_CONNECT_FORBIDDEN）。判断只看 bind.env，未绑定环境的 profile 不触发熔断。
3. **行数上限**：`--max` 默认 500，clamp 到 [1, 5000]。
4. **会话级只读加固**：建连后执行 `SET SESSION TRANSACTION READ ONLY` 作为第二道防线（失败仅 warning，不阻断——部分代理库不支持）。

## D6. CLI 参数变更

- `seek db query`：位置参数 `database` 改为 `nargs="?"`；新增 `--conn`、`--project`、`--env`、`--max`、`--i-know-this-is-prod`。
- `seek db tables` / `seek db schema`：同样加 `--conn/--project/--env`；本地路径时 `tables` 不需要 database 位置参数（profile 自带）。
- `seek db conn add/list/test/remove`：新增子命令组。
- 参数互斥校验：`--conn` 与位置参数 database 不得同时提供。

## D7. 输出格式

本地查询 success data：

```json
{"backend": "local", "conn": "<profile>", "columns": ["..."], "rows": [[...]],
 "rowCount": 42, "truncated": false}
```

`backend` 字段显式标注来源，供 agent 区分证据可信路径；其余字段语义与 DMS 对齐。

## D8. capabilities 与 doctor

- `capabilities.py`：注册 `db conn add/list/test/remove` 与扩展后的 query/tables/schema 参数 schema。
- `doctor`：新增 db.json 检查项——结构校验始终执行；连通性测试仅在非 `--no-live` 时执行（逐 profile SELECT 1，失败记 warning 不 fail 整体）。

## D9. 测试策略

`cli/tests/test_db_local.py`（unittest，与现有测试风格一致）：
- profile 读写：add/list/remove、0600 权限、env: 密码原样存储、list 脱敏（用临时 HOME 隔离）。
- 寻址分发：`--conn` 优先、bind 反查唯一/多匹配/无匹配、无参数回落 DMS（mock dms_client）。
- 安全：非只读 SQL 拒绝且不建连（mock 断言 connect 未调用）、生产熔断拒绝与放行、max_rows clamp 与截断（mock 游标 fetchmany）。
- 驱动缺失指引：patch import 失败路径断言错误文案含安装指引。
全部 mock 掉 pymysql，测试不需要真实数据库。
