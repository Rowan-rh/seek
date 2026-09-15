# Design: fix-cr-hardening-r1

## D1. SQL 锁定读拦截（commands/db.py）

`_FORBIDDEN_SQL_RE` 追加两个多词分支：`FOR\s+SHARE`（MySQL 8.0+）与 `LOCK\s+IN\s+SHARE\s+MODE`（旧语法）。正则先经 `_strip_sql_comments_and_literals` 剥离注释与字面量再匹配，多词空白变形天然覆盖。其余校验路径（多语句、可执行注释、前缀白名单）不动。

## D2. 会话写原子性（chain.py）

- `_save_session(session)` 拆两层：
  - `_write_session_file(session)`：纯写入原语（mkstemp → dump → fsync → os.replace），**不持锁**；
  - `_save_session(session)`：`with _session_lock(...)` 包 `_write_session_file`，供 start_session 等无外部锁调用方使用。
- `complete_step` / `amend_step` / `provide_inputs` 改为：
  ```python
  with _session_lock(session_id):
      session = get_session(session_id)   # 锁内读
      ...校验与内存修改...
      _write_session_file(session)        # 锁内写
  ```
- **关键约束**：锁内不得再调用会获取同一把锁的函数——flock 以 open file description 为持有单位，同进程用新 fd 二次 LOCK_EX 会死锁。`complete_step` 锁内调用的 `validate_step` 只读不写（内部 get_session 纯读盘），安全；`_save_session`（带锁版）不出现在锁内路径。
- 锁文件路径 `{session_id}.lock` 不变；fcntl 语义跨进程，新旧版本 CLI 混跑仍互斥。

## D3. 错误码与日志加固

- `cmd_project_add`：把 `_build_env_config` 三次调用包进 try/except ValueError → `error(str(e), code="BAD_ARGUMENT")`。此前实测落入 `cli.main()` 兜底 INTERNAL_ERROR，误导 agent 重试策略。
- `error_log.log_error` 的 `context` 落盘前过 `_sanitize_context`：dict 时顶层敏感键（复用 args 的键集）打码、字符串值截断 2000 字符；非 dict 序列化后截断。args 逻辑同步改用共享 `_mask_value`，消除同一函数内两套口径。

## D4. utils.py 抽取

新增 `seek_cli/utils.py`：

- `file_lock(lock_path)`：fcntl 排他锁 contextmanager（ImportError 降级无锁），六个模块（settings/config/db_store/chain/error_log/perf_log）的私有实现替换为对它的调用；**各模块锁路径计算不变**（`<config>.lock` / `errors.lock` / `perf.lock` / `<session_id>.lock`）。
- `atomic_write_json(path, data, *, indent=2, default=None, chmod_0600=False)`：mkstemp → json.dump → fsync →（可选 chmod）→ os.replace；异常时清理临时文件。settings/config/db_store/chain 四处 JSON 写入替换为对它的调用；db_store 传 chmod_0600=True。
- `atomic_write_text(path, text)`：error_log.clear_errors 的空文件替换复用。
- 临时文件前缀统一为 `.<name>-`（原各模块前缀不同但均为不可见临时产物，无契约影响）。

## D5. 私有成员公共化（保留下划线别名）

| 模块 | 公共名 | 别名保留原因 |
|------|--------|-------------|
| chain | `PROBLEM_DESCRIPTION_INPUTS` | test_doc_consistency 引用 `_PROBLEM_DESCRIPTION_INPUTS` |
| expert_client / roar_client | `DEFAULT_HOST` | config_cmd 引用 |
| sls_client | `SDK_AVAILABLE` / `get_log_client` / `parse_time_range` | doctor 与 perf 命令引用；test_retro_batch 引用 `_parse_time_range` |

命令层调用点（commands/chain.py、config_cmd.py、doctor.py、commands/perf.py、perf_log.py）切换公共名；定义改为公共名 + 一行别名赋值，存量测试零改动。

## D6. 种子配置可移植性

两份副本（`cli/config/projects.json` 与 `cli/seek_cli/resources/config/projects.json`）的 14 个 `repoPath` 置空。`trace call-chain` 回退 `_WORKSPACE/<project>`，标准 checkout 布局（qitian_ali/<project>）下解析结果与原绝对路径一致，本机行为不变；镜像一致性测试继续守护两份副本逐字节相同。用户自定义路径走用户级 `~/.seek/config/projects.json` 覆盖。

## D7. 测试策略

- 锁定读：`test_hardening.py` 的 SQL 校验用例组补 `LOCK IN SHARE MODE`、`FOR SHARE`、`FOR UPDATE OF t` 三条拒绝断言。
- 会话原子性：`test_chain_persistence.py` 新增并发注入用例——patch `chain.get_session` 加 50ms 延迟放大窗口，4 线程 barrier 同时 `provide_inputs` 注入不同键，断言全部键落盘（修复前该用例确定性失败：读到修改前快照互相覆盖）。
- BAD_ARGUMENT：`test_reliability.py` 补 `--sls-daily` 非法格式的错误码断言。
- error_log：补 context 敏感键打码与长值截断断言。
- 回归：全量 `python -m unittest discover cli/tests`（187 用例 + 新增），重点 test_unified_config / test_db_local / test_chain_persistence / test_reliability 守护 utils 重构不改变行为。

## D8. 边界

- 不改任何 stdout JSON 契约与既有成功路径行为；`project add` 非法参数的 error code 从 INTERNAL_ERROR 变为 BAD_ARGUMENT 属错误语义修正（CLI 退出码均为 1）。
- alias 保留一个版本周期，后续 change 清理。
