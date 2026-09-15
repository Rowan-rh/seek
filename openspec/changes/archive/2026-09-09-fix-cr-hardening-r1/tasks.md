# Tasks: fix-cr-hardening-r1

## 1. P2 修复

- [x] 1.1 `_FORBIDDEN_SQL_RE` 补 `FOR SHARE` / `LOCK IN SHARE MODE`；test_hardening 补三条锁定读拒绝断言（含 `FOR UPDATE OF t`）
- [x] 1.2 chain.py 拆 `_write_session_file`（无锁原语）；`complete_step`/`amend_step`/`provide_inputs` 改锁内读-改-写
- [x] 1.3 test_chain_persistence 补并发注入用例（延迟放大窗口 + 多线程 barrier + 全键落盘断言）

## 2. P3 加固包

- [x] 2.1 `cmd_project_add` 捕获 ValueError → BAD_ARGUMENT；test_reliability 补断言
- [x] 2.2 error_log context 落盘脱敏（敏感键打码）+ 2000 字符截断；补测试
- [x] 2.3 新增 `seek_cli/utils.py`（file_lock / atomic_write_json / atomic_write_text），六个模块切换，锁路径与 0600 语义不变
- [x] 2.4 私有成员公共化 + 别名：chain.PROBLEM_DESCRIPTION_INPUTS、expert/roar DEFAULT_HOST、sls_client SDK_AVAILABLE/get_log_client/parse_time_range；命令层调用点切换
- [x] 2.5 种子配置两份副本 14 个 repoPath 置空（镜像字节一致）
- [x] 2.6 `.gitignore` 补 `.env*`

## 3. 版本与验证

- [x] 3.1 `__init__.py` 版本 0.4.5 + CHANGELOG 条目
- [x] 3.2 `python3 -m seek_cli version` 启动正常
- [x] 3.3 `python3 -m unittest discover cli/tests` 全绿
- [x] 3.4 冒烟：`seek db query --conn x --sql 'SELECT * FROM t LOCK IN SHARE MODE'` 拒绝；并发注入用例在修复前代码上验证过会失败（红→绿确认）
