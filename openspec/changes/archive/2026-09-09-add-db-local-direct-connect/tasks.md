# Tasks: add-db-local-direct-connect

## 1. 连接 profile 存储层

- [x] 1.1 新建 `cli/seek_cli/integrations/db_store.py`：db.json 读写（load/add/remove/list），fcntl 锁 + tempfile 原子替换 + chmod 0600，bind 反查函数 `find_by_bind(project, env)`
- [x] 1.2 密码解析：`env:VAR` 前缀读环境变量（缺失时报明确错误），明文原样使用

## 2. 本地直连客户端

- [x] 2.1 新建 `cli/seek_cli/integrations/db_local.py`：`LocalDbClient`（test/list_tables/table_schema/query/close），延迟 import pymysql，缺失时抛带安装指引的 RuntimeError
- [x] 2.2 连接参数硬约束（connect_timeout=5/read_timeout=30/utf8mb4/autocommit）与 `SET SESSION TRANSACTION READ ONLY` 加固（失败仅 warning）
- [x] 2.3 行数限制：`fetchmany(max_rows+1)` 实现截断与 truncated 标记

## 3. 命令层

- [x] 3.1 `cli/seek_cli/commands/db.py`：新增 `_resolve_local_profile(args)` 分发逻辑与 `cmd_db_conn_add/list/test/remove`
- [x] 3.2 `cmd_db_query/tables/schema` 接入本地 backend：只读校验前置、生产熔断（PROD_DIRECT_CONNECT_FORBIDDEN）、`--max` clamp [1,5000]、输出含 backend/conn/columns/rows/rowCount/truncated
- [x] 3.3 `cli/seek_cli/cli.py`：db query/tables/schema 增加 --conn/--project/--env/--max/--i-know-this-is-prod，database 改可选；注册 conn 子命令组与参数互斥校验

## 4. 能力发现与体检

- [x] 4.1 `cli/seek_cli/commands/capabilities.py`：注册 db conn 与扩展参数 schema
- [x] 4.2 `cli/seek_cli/commands/doctor.py`：db.json 结构校验 + 非 --no-live 时逐 profile 连通性检查

## 5. 打包与测试

- [x] 5.1 `cli/setup.py`：extras_require 增加 `mysql: PyMySQL>=1.1`
- [x] 5.2 新建 `cli/tests/test_db_local.py`：profile 读写/0600/脱敏、寻址分发优先级、bind 反查、只读校验不建连、生产熔断、行数截断、驱动缺失指引（全部 mock pymysql，临时 HOME 隔离）
- [x] 5.3 运行 `python -m unittest discover cli/tests` 全绿

## 6. 文档与验证

- [x] 6.1 `SKILL.md` 与 `references/command-reference.md`：补充本地直连命令与「日常优先直连、生产走 DMS」路由指引
- [x] 6.2 `cli/README.md`：db 章节补充 conn 用法示例
- [x] 6.3 `openspec validate --strict add-db-local-direct-connect` 通过
