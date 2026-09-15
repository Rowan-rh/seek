# Tasks: fix-skill-update-consistency

## 1. 版本一致性校验（cli/seek_cli/commands/skill.py）

- [x] 1.1 `_get_source_info` 读取 `cli_version_ref`，新增 `_version_consistency()` 三态判定（True/False/None）
- [x] 1.2 `cmd_skill_update`/`cmd_skill_status` data 顶层输出 `version_consistency`；不一致时 message 追加告警、`up_to_date` note 标注，命令仍 `status=ok`

## 2. 逐目录失败隔离（cli/seek_cli/commands/skill.py）

- [x] 2.1 `broken`/`foreign`/`not_found` 分支各自 `try/except OSError`，失败标 `status=error` 并继续；`fixed` 只统计成功项

## 3. 迁移分阶段标注（cli/seek_cli/commands/skill.py）

- [x] 3.1 备份与删除/建链拆两段：备份失败 `backup_failed`；其后失败 `migration_failed` 且携带 `backup` 路径

## 4. 源标识如实化（cli/seek_cli/commands/skill.py）

- [x] 4.1 `_get_source_info` 增加 `source_dirty`（`git status --porcelain` 非空），`update`/`status` 顶层透传

## 5. status --dir 与文案（cli/seek_cli/cli.py、capabilities.py）

- [x] 5.1 `skill status` 增加 `--dir`；capabilities 声明 status args 同步 `--dir`
- [x] 5.2 `install --dir` 帮助文案改为两个默认目录

## 6. 测试

- [x] 6.1 `test_skill_management.py` 新增：漂移检出告警、一致静默、未声明视为未知、逐目录隔离、迁移分阶段含 backup 路径、status --dir、dirty 标记（含 `skill.__version__` 的保存/恢复）
- [x] 6.2 补齐 `test_hardening.py` doctor 测试对 `_db_conn_checks` 的 mock（原测试泄漏到真实 `~/.seek/config/db.json` 的 ~150 个 MySQL profile，网络受限时 `poll()` 永久挂起，阻断全量回归；与技能命令无关但阻塞验证）
- [x] 6.3 `python -m unittest discover cli/tests` 全绿：145 tests OK（含 capabilities 契约）

## 7. 文档与验证

- [x] 7.1 文档同步：`references/command-reference.md` 无 skill 条目（不涉及）；`cli/README.md` 补 `update`/`status --dir` 与新输出契约
- [x] 7.2 真实 CLI 端到端：`seek skill status --dir ~/.qoder/skills` 生效；`seek skill update` 对当前仓库如实报告 `版本声明不匹配: cli_version_ref=0.5.0 ≠ 实际 0.4.0`，`source_dirty: true`、commit 标识正常
- [x] 7.3 `openspec validate fix-skill-update-consistency --strict` 通过
