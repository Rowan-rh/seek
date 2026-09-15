# Proposal: fix-cr-hardening-r1

## Why

2026-09-09 整体 CR（CR报告-seek-2026-09-09-qoder.md）确认代码库整体评级 A（无 P0/P1），但遗留 2 个真实 P2 与一组 P3 加固项，趁上下文新鲜集中修一轮：

- **P2-1 只读 SQL 校验绕过**：`FOR UPDATE` 已拦截，但 `LOCK IN SHARE MODE`、`FOR SHARE`（MySQL 8）实测可绕过，与 CHANGELOG 0.3.1「拒绝锁定查询」声明不符。
- **P2-2 chain 会话读-改-写不原子**：`complete_step`/`amend_step`/`provide_inputs` 三个写入口读在锁外（`_session_lock` 只覆盖写入段），并发操作同一会话丢更新。
- **P3 加固包**：`seek project add` 参数错误落入 INTERNAL_ERROR（应 BAD_ARGUMENT）；error_log 的 context 字段不脱敏不截断；file_lock/atomic_write 六处同构重复；三处私有 API 跨模块访问；种子配置 14 个项目 repoPath 为个人绝对路径（AGENT.md 已列为已知待整改）；`.gitignore` 缺 `.env*`。

## What Changes

- **SQL 校验**：`_FORBIDDEN_SQL_RE` 补 `FOR SHARE` 与 `LOCK IN SHARE MODE` 两种锁定读语法 + 回归测试。
- **会话写原子性**：`_save_session` 拆出锁内写入原语 `_write_session_file`，`complete_step`/`amend_step`/`provide_inputs` 改为锁内「读-改-写」全流程；新增并发注入回归测试。锁文件路径不变，新旧版本进程混跑仍互斥。
- **错误码语义**：`cmd_project_add` 捕获 `_build_env_config` 的 `ValueError`，返回 `BAD_ARGUMENT`。
- **error_log 加固**：context 落盘前复用敏感键打码规则并截断长值（2000 字符）。
- **utils 抽取**：新增 `seek_cli/utils.py`（`file_lock` + `atomic_write_json`/`atomic_write_text`），收敛 settings/config/db_store/chain/error_log/perf_log 六处锁与四处 JSON 原子写；锁路径与语义保持逐字节不变。
- **公共化私有成员**：`chain.PROBLEM_DESCRIPTION_INPUTS`、`expert_client.DEFAULT_HOST`、`roar_client.DEFAULT_HOST`、`sls_client.SDK_AVAILABLE/get_log_client/parse_time_range` 转为公共名（保留下划线别名兼容存量测试），命令层调用点切换公共名。
- **可移植性**：种子配置两份副本的 14 个 `repoPath` 置空（`trace call-chain` 的 workspace 相对回退路径在标准 checkout 布局下解析结果不变）；`.gitignore` 补 `.env*`。

## Capabilities

### New Capabilities
- `chain-session-persistence`: 会话状态文件的写原子性规范——写入口锁覆盖完整读-改-写周期。

### Modified Capabilities
- `db-local-connections`: 「只读 SQL 校验复用」需求扩展为拒绝全部锁定读语法（含 FOR SHARE / LOCK IN SHARE MODE）。

## Impact

- **代码**：`commands/db.py`、`chain.py`、`commands/project.py`、`error_log.py`、新增 `utils.py` 并重构 `settings.py`/`config.py`/`db_store.py`/`perf_log.py`/`error_log.py` 的锁与写入、`commands/chain.py`/`config_cmd.py`/`doctor.py`/`commands/perf.py` 调用点公共名切换、种子配置两份副本。
- **测试**：`test_hardening.py` 补锁定读用例；`test_chain_persistence.py` 补并发注入用例；`test_reliability.py` 补 project add BAD_ARGUMENT 与 error_log context 脱敏用例。
- **文档**：CHANGELOG + 版本 0.4.5；`.gitignore`。
- **Out of scope**：doctor/串行 I/O 并行化、capabilities 自动生成、`_build_parser` 拆分（CR P3 观察项，另立 change）；dms 等待循环总时限；session gc。
