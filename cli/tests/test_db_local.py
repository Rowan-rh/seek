"""本地直连数据库（seek db --conn / db conn）回归测试

全部 mock 掉 pymysql，无需真实数据库；用临时目录 patch db_store.DB_FILE 隔离。
"""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from seek_cli.commands import db
from seek_cli.integrations import db_store, db_local


def _profile(env="daily", password="env:TEST_DB_PWD"):
    return {
        "type": "mysql", "host": "127.0.0.1", "port": 3306,
        "database": "qt_stability", "user": "qt_read", "password": password,
        "bind": {"project": "qt-stability", "env": env},
    }


class DbStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_file = db_store.DB_FILE
        db_store.DB_FILE = Path(self.temp_dir.name) / "db.json"

    def tearDown(self):
        db_store.DB_FILE = self.old_db_file
        self.temp_dir.cleanup()

    def test_add_writes_file_with_0600_and_required_fields(self):
        db_store.add_connection("daily-db", _profile())
        self.assertTrue(db_store.DB_FILE.exists())
        mode = stat.S_IMODE(os.stat(db_store.DB_FILE).st_mode)
        self.assertEqual(0o600, mode)
        profile = db_store.get_connection("daily-db")
        self.assertEqual("env:TEST_DB_PWD", profile["password"])
        self.assertEqual({"project": "qt-stability", "env": "daily"}, profile["bind"])

    def test_add_rejects_missing_fields_and_bad_port_and_bad_type(self):
        with self.assertRaises(db_store.DbStoreError):
            db_store.add_connection("bad", {"type": "mysql"})
        bad_port = _profile()
        bad_port["port"] = 99999
        with self.assertRaises(db_store.DbStoreError):
            db_store.add_connection("bad", bad_port)
        bad_type = _profile()
        bad_type["type"] = "oracle"
        with self.assertRaises(db_store.DbStoreError):
            db_store.add_connection("bad", bad_type)

    def test_remove_returns_false_for_unknown(self):
        self.assertFalse(db_store.remove_connection("nope"))
        db_store.add_connection("daily-db", _profile())
        self.assertTrue(db_store.remove_connection("daily-db"))

    def test_find_by_bind_matches_project_and_env(self):
        db_store.add_connection("a", _profile())
        db_store.add_connection("b", _profile(env="pre"))
        self.assertEqual(["a"], [n for n, _ in db_store.find_by_bind("qt-stability", "daily")])
        self.assertEqual([], db_store.find_by_bind("qt-stability", "prod"))

    def test_resolve_password_env_and_plain(self):
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            self.assertEqual("s3cret", db_store.resolve_password(_profile()))
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TEST_DB_PWD", None)
            with self.assertRaises(db_store.DbStoreError):
                db_store.resolve_password(_profile())
        self.assertEqual("plain", db_store.resolve_password(_profile(password="plain")))

    def test_is_prod_env_rules(self):
        self.assertTrue(db_store.is_prod_env(_profile(env="prod")))
        self.assertTrue(db_store.is_prod_env(_profile(env="online")))
        self.assertTrue(db_store.is_prod_env(_profile(env="publish_aso")))
        self.assertFalse(db_store.is_prod_env(_profile(env="daily")))
        self.assertFalse(db_store.is_prod_env(_profile(env="pre")))
        self.assertFalse(db_store.is_prod_env({"bind": None}))


class ConnCommandTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_file = db_store.DB_FILE
        db_store.DB_FILE = Path(self.temp_dir.name) / "db.json"

    def tearDown(self):
        db_store.DB_FILE = self.old_db_file
        self.temp_dir.cleanup()

    def _add_args(self, name="daily-db", password="env:TEST_DB_PWD"):
        return SimpleNamespace(name=name, type="mysql", host="127.0.0.1", port=3306,
                               database="qt_stability", user="qt_read", password=password,
                               project="qt-stability", env="daily")

    def test_conn_add_list_remove_flow_with_masked_password(self):
        result = db.cmd_db_conn_add(self._add_args(password="plaintext-secret"))
        self.assertEqual("ok", result["status"])

        result = db.cmd_db_conn_list(SimpleNamespace())
        self.assertEqual("ok", result["status"])
        item = result["data"]["connections"][0]
        self.assertNotEqual("plaintext-secret", item["password"])
        self.assertIn("*", item["password"])

        result = db.cmd_db_conn_remove(SimpleNamespace(name="daily-db"))
        self.assertEqual("ok", result["status"])
        result = db.cmd_db_conn_remove(SimpleNamespace(name="daily-db"))
        self.assertEqual("error", result["status"])

    def test_conn_add_invalid_returns_error(self):
        args = self._add_args()
        args.port = 0
        result = db.cmd_db_conn_add(args)
        self.assertEqual("error", result["status"])
        self.assertEqual("DB_STORE_ERROR", result["error"]["code"])

    def test_conn_test_missing_profile(self):
        result = db.cmd_db_conn_test(SimpleNamespace(name="nope"))
        self.assertEqual("error", result["status"])
        self.assertEqual("DB_STORE_ERROR", result["error"]["code"])


class QueryDispatchTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_file = db_store.DB_FILE
        db_store.DB_FILE = Path(self.temp_dir.name) / "db.json"

    def tearDown(self):
        db_store.DB_FILE = self.old_db_file
        self.temp_dir.cleanup()

    def _query_args(self, **kw):
        base = dict(database=None, sql="SELECT 1", conn=None, project=None, env=None,
                    max=500, i_know_this_is_prod=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def _mock_pymysql(self, rows, columns=("id", "name")):
        """构造 mock pymysql 模块，返回 (patcher, cursor_mock)"""
        cur = MagicMock()
        cur.description = [(c,) for c in columns]
        cur.fetchmany.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        pm = MagicMock()
        pm.connect.return_value = conn
        patcher = patch.object(db_local, "_import_pymysql", return_value=pm)
        return patcher, cur

    def test_non_readonly_sql_rejected_without_connect(self):
        db_store.add_connection("daily-db", _profile())
        patcher, _ = self._mock_pymysql([])
        patcher.start()
        try:
            result = db.cmd_db_query(self._query_args(conn="daily-db", sql="UPDATE t SET a=1"))
        finally:
            patcher.stop()
        self.assertEqual("error", result["status"])
        self.assertEqual("READ_ONLY_SQL_REQUIRED", result["error"]["code"])

    def test_prod_profile_refused_without_confirmation(self):
        db_store.add_connection("prod-db", _profile(env="prod"))
        result = db.cmd_db_query(self._query_args(conn="prod-db"))
        self.assertEqual("error", result["status"])
        self.assertEqual("PROD_DIRECT_CONNECT_FORBIDDEN", result["error"]["code"])

    def test_local_query_returns_columns_rows_truncated(self):
        db_store.add_connection("daily-db", _profile())
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            patcher, cur = self._mock_pymysql([(1, "a"), (2, "b"), (3, "c")])
            patcher.start()
            try:
                result = db.cmd_db_query(self._query_args(conn="daily-db", max=2))
            finally:
                patcher.stop()
        self.assertEqual("ok", result["status"])
        data = result["data"]
        self.assertEqual("local", data["backend"])
        self.assertEqual(["id", "name"], data["columns"])
        self.assertEqual(2, data["rowCount"])
        self.assertTrue(data["truncated"])
        cur.fetchmany.assert_called_once_with(3)  # max_rows + 1

    def test_max_rows_clamped_to_hard_limit(self):
        db_store.add_connection("daily-db", _profile())
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            patcher, cur = self._mock_pymysql([])
            patcher.start()
            try:
                db.cmd_db_query(self._query_args(conn="daily-db", max=99999))
            finally:
                patcher.stop()
        cur.fetchmany.assert_called_once_with(5001)  # 5000 + 1

    def test_bind_lookup_resolves_unique_profile(self):
        db_store.add_connection("daily-db", _profile())
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            patcher, _ = self._mock_pymysql([(1, "a")])
            patcher.start()
            try:
                result = db.cmd_db_query(self._query_args(project="qt-stability", env="daily"))
            finally:
                patcher.stop()
        self.assertEqual("ok", result["status"])
        self.assertEqual("daily-db", result["data"]["conn"])

    def test_bind_lookup_multiple_matches_error(self):
        db_store.add_connection("a", _profile())
        db_store.add_connection("b", _profile())
        result = db.cmd_db_query(self._query_args(project="qt-stability", env="daily"))
        self.assertEqual("error", result["status"])
        self.assertIn("多个 profile", result["error"]["message"])

    def test_bind_lookup_no_match_error(self):
        result = db.cmd_db_query(self._query_args(project="nobody", env="daily"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_positional_database_falls_back_to_dms(self):
        with patch.object(db.dms_client, "call_dms", return_value={"rows": []}) as mock_dms:
            result = db.cmd_db_query(self._query_args(database="12345"))
        self.assertEqual("ok", result["status"])
        mock_dms.assert_called_once()
        self.assertEqual("executeScript", mock_dms.call_args[0][0])

    def test_conn_and_positional_mutually_exclusive(self):
        db_store.add_connection("daily-db", _profile())
        result = db.cmd_db_query(self._query_args(conn="daily-db", database="12345"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_missing_target_error(self):
        result = db.cmd_db_query(self._query_args())
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_driver_missing_gives_install_hint(self):
        db_store.add_connection("daily-db", _profile())
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            with patch.object(db_local, "_import_pymysql",
                              side_effect=RuntimeError(db_local._INSTALL_HINT)):
                result = db.cmd_db_query(self._query_args(conn="daily-db"))
        self.assertEqual("error", result["status"])
        self.assertEqual("DB_DRIVER_MISSING", result["error"]["code"])
        self.assertIn("pip install", result["error"]["message"])

    def test_conn_test_success(self):
        db_store.add_connection("daily-db", _profile())
        with patch.dict(os.environ, {"TEST_DB_PWD": "s3cret"}):
            patcher, _ = self._mock_pymysql([(1,)])
            patcher.start()
            try:
                result = db.cmd_db_conn_test(SimpleNamespace(name="daily-db"))
            finally:
                patcher.stop()
        self.assertEqual("ok", result["status"])
        self.assertTrue(result["data"]["ok"])


if __name__ == "__main__":
    unittest.main()
