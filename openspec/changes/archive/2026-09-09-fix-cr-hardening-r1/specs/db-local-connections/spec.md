# Delta: db-local-connections

## MODIFIED Requirements

### Requirement: 只读 SQL 校验复用
本地直连路径 SHALL 复用 DMS 路径相同的只读 SQL 校验规则：仅允许单条 SELECT/WITH/EXPLAIN，拒绝 DML/DDL/事务控制/多语句/可执行注释，以及全部锁定读语法（FOR UPDATE、FOR SHARE、LOCK IN SHARE MODE）。

#### Scenario: 非只读 SQL 被拒绝
- **WHEN** 通过 --conn 执行 `UPDATE ...` 或多语句 SQL
- **THEN** 返回 READ_ONLY_SQL_REQUIRED 错误，且不建立数据连接

#### Scenario: 锁定读被拒绝
- **WHEN** 通过 --conn 执行 `SELECT * FROM t LOCK IN SHARE MODE`、`SELECT * FROM t FOR SHARE` 或 `SELECT * FROM t FOR UPDATE OF t`
- **THEN** 返回 READ_ONLY_SQL_REQUIRED 错误，且不建立数据连接
