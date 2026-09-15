"""本地数据库直连客户端 — 日常/预发环境 DB 取证

与 DMS MCP 路径并行的 backend：本机网络直连 MySQL，无 DMS 网关中转。
一期仅支持 MySQL（PyMySQL），按 profile.type 分支，后续可扩展 PostgreSQL。

安全约束（与 commands/db.py 配合）：
- 只读 SQL 校验在命令层前置执行，非法 SQL 不触达本模块
- 建连后执行 SET SESSION TRANSACTION READ ONLY 作为第二道防线
- 行数限制通过 fetchmany(max_rows+1) 实现，不全量拉取
"""

import sys
from typing import Optional

from seek_cli.integrations import db_store

# 连接硬约束：避免 CLI 因网络问题长时间挂起
_CONNECT_TIMEOUT = 5
_READ_TIMEOUT = 30
_INSTALL_HINT = (
    "PyMySQL 未安装。安装方式: pip install seek-cli[mysql] 或 pip install pymysql"
)


def _import_pymysql():
    """延迟 import PyMySQL，缺失时抛带安装指引的 RuntimeError"""
    try:
        import pymysql
        return pymysql
    except ImportError as exc:
        raise RuntimeError(_INSTALL_HINT) from exc


class LocalDbClient:
    """本地 MySQL 直连客户端（每命令一连接，用完即关）"""

    def __init__(self, name: str, profile: dict):
        self.name = name
        self.profile = profile
        self._conn = None

    def _connect(self):
        if self._conn is not None:
            return self._conn
        pymysql = _import_pymysql()
        password = db_store.resolve_password(self.profile)
        try:
            self._conn = pymysql.connect(
                host=self.profile["host"],
                port=int(self.profile["port"]),
                user=self.profile["user"],
                password=password,
                database=self.profile["database"],
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=_CONNECT_TIMEOUT,
                read_timeout=_READ_TIMEOUT,
            )
        except Exception as exc:
            raise RuntimeError(
                f"连接失败 {self.profile['host']}:{self.profile['port']}"
                f"/{self.profile['database']}: {exc}"
            ) from exc
        # 会话级只读加固（失败仅 warning，部分代理库/网关不支持该语句）
        try:
            with self._conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
        except Exception as exc:
            print(f"[seek] ⚠️ 会话只读加固失败(不阻断): {exc}", file=sys.stderr)
        return self._conn

    def test(self) -> dict:
        """连通性测试：SELECT 1"""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True, "target": f"{self.profile['host']}:{self.profile['port']}/{self.profile['database']}"}

    def list_tables(self) -> list:
        """列出当前库全部表"""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            return [row[0] for row in cur.fetchall()]

    def table_schema(self, table: str) -> dict:
        """获取表结构：建表语句 + 列信息"""
        conn = self._connect()
        database = self.profile["database"]
        with conn.cursor() as cur:
            cur.execute("SHOW CREATE TABLE `%s`" % table.replace("`", ""))
            row = cur.fetchone()
            create_sql = row[1] if row else None
            cur.execute(
                "SELECT column_name, column_type, is_nullable, column_key, "
                "column_default, column_comment FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (database, table),
            )
            columns = [
                {
                    "name": r[0], "type": r[1], "nullable": r[2],
                    "key": r[3], "default": r[4], "comment": r[5],
                }
                for r in cur.fetchall()
            ]
        return {"table": table, "database": database,
                "createSql": create_sql, "columns": columns}

    def query(self, sql: str, max_rows: int = 500) -> dict:
        """执行只读 SQL（命令层已校验），返回 columns/rows/rowCount/truncated"""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
            columns = [desc[0] for desc in cur.description] if cur.description else []
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]
        # 行内值统一转 JSON 可序列化形态（datetime/Decimal/bytes 等）
        serialized = [[_jsonable(v) for v in row] for row in rows]
        return {
            "columns": columns,
            "rows": serialized,
            "rowCount": len(serialized),
            "truncated": truncated,
        }

    def close(self) -> None:
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        try:
            conn.close()
        except Exception:
            pass


def _jsonable(value):
    """把 MySQL 返回值转为 JSON 可序列化形态"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def open_client(name: str, profile: Optional[dict] = None) -> LocalDbClient:
    """便捷构造：profile 缺省时按名称从 db.json 读取"""
    if profile is None:
        profile = db_store.get_connection(name)
        if profile is None:
            available = ", ".join(sorted(db_store.load_connections())) or "无"
            raise db_store.DbStoreError(
                f"连接 profile '{name}' 不存在（现有: {available}），"
                "可用 seek db conn add 创建"
            )
    return LocalDbClient(name, profile)
