"""SLS 查询命令回归测试。"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli.commands import sls


class SlsQueryTest(unittest.TestCase):
    def _args(self, **overrides):
        values = {
            "project": None,
            "env": None,
            "endpoint": "cn-hangzhou.log.aliyuncs.com",
            "sls_project": "qt-changeplatform",
            "logstore": "qt-change-planning-production",
            "query": "uuid-1",
            "time": "15m",
            "max": 100,
            "sort": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_direct_mode_queries_bare_sls_target(self):
        response = {"logs": [{"__time__": "2"}], "count": 1}
        with patch.object(sls.sls_client, "query_logs", return_value=response) as query_logs:
            result = sls.cmd_sls_query(self._args())
        self.assertEqual("ok", result["status"])
        self.assertEqual("direct", result["data"]["mode"])
        self.assertFalse(result["data"]["truncated"])
        query_logs.assert_called_once_with(
            endpoint="cn-hangzhou.log.aliyuncs.com",
            project="qt-changeplatform",
            logstore="qt-change-planning-production",
            query="uuid-1",
            time_range="15m",
            max_results=100,
        )

    def test_direct_mode_requires_complete_target(self):
        result = sls.cmd_sls_query(self._args(logstore=None))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_configured_mode_requires_project_and_environment(self):
        result = sls.cmd_sls_query(self._args(endpoint=None, sls_project=None, logstore=None))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_max_limit_and_truncation_warning(self):
        result = sls.cmd_sls_query(self._args(max=1001))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

        response = {"logs": [{"__time__": "1"}] * 100, "count": 100}
        with patch.object(sls.sls_client, "query_logs", return_value=response):
            result = sls.cmd_sls_query(self._args())
        self.assertTrue(result["data"]["truncated"])
        self.assertIn("may be incomplete", result["data"]["warnings"][0])

    def test_sort_orders_logs_by_time(self):
        response = {
            "logs": [{"__time__": "2"}, {"__time__": "1"}],
            "count": 2,
        }
        with patch.object(sls.sls_client, "query_logs", return_value=response):
            result = sls.cmd_sls_query(self._args(sort="asc"))
        self.assertEqual(["1", "2"], [log["__time__"] for log in result["data"]["logs"]])
        self.assertEqual("asc", result["data"]["sort"])


if __name__ == "__main__":
    unittest.main()
