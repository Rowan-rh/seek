# Design: fix-skill-update-consistency

## D1. 版本一致性校验（破除"假对齐"）

现状：`_link_status` 只比较符号链接解析目标是否等于 `_SEEK_ROOT`（[skill.py:44](file:///Users/admin/Documents/code/qitian_ali/seek/cli/seek_cli/commands/skill.py#L44)）；`cmd_skill_update`/`cmd_skill_status` 结果中的版本字段全部回显 `_get_source_info()` 源侧值，`cli_version_ref` 无任何消费方。

方案：

1. `_get_source_info` 增加读取 `cli_version_ref = _frontmatter_value("cli_version_ref")`。
2. 新增模块级 `_version_consistency(source_info) -> dict`：

```python
def _version_consistency(source_info: dict) -> dict:
    declared = source_info.get("cli_version_ref") or None
    actual = source_info["cli_version"]
    return {
        "declared_cli_version": declared,
        "actual_cli_version": actual,
        "consistent": (declared == actual) if declared else None,
    }
```

- `consistent` 三态：`True` 一致 / `False` 漂移 / `None` frontmatter 未声明（不告警）。
- 比较对象用模块顶部 `from seek_cli import __version__` 绑定值（`source_info["cli_version"]`），与 `seek version` 输出同源；测试可替换模块属性。
3. `update`/`status` 的 data 顶层增加 `version_consistency` 与 `source_dirty`；`consistent is False` 时：
   - message 追加告警：`"；版本声明不匹配: cli_version_ref={declared} ≠ 实际 {actual}"`；
   - `up_to_date` 条目的 note 追加 `"（声明 cli_version_ref {declared} ≠ 实际 {actual}）"`。
4. **告警 ≠ 失败**：命令仍 `status=ok`、退出码 0。理由：链接拓扑正确、命令职责已完成；版本漂移是内容治理问题，用非零退出码会让管道把"有告警的健康状态"当故障。agent 可读 `data.version_consistency.consistent` 做后续决策。

## D2. 逐目录失败隔离

现状：`broken`/`foreign`/`not_found` 分支的 `unlink()` + `_install_link()` 无保护，任一目录抛 `OSError` 会中断整个循环，已累积 `results` 全部丢失（复验确认第一个目录已被静默改写）。

方案：三个分支各自包 `try/except OSError`，失败时 `entry.update(status="error", valid=False, error=str(exc))` 并 `continue` 语义（循环自然继续），`fixed` 只统计成功项。`directory` 分支已有保护，维持结构但对齐异常处理。

不做回滚：`broken` 链接删除后建链失败，目标停留在 `not_found`，重跑 `update` 即安装——比"回滚成 broken"更利于收敛，且在 entry 中如实标注即可。

## D3. 迁移分阶段标注

现状：备份/删除/建链三步一个 except，备份成功后任何失败都标 `backup_failed`，丢失已生成的备份路径。

方案：拆两段——

```python
try:
    backup = _backup_directory(link)
except (OSError, tarfile.TarError) as exc:
    entry.update(status="backup_failed", valid=False, error=str(exc))
else:
    try:
        shutil.rmtree(link)
        _install_link(link)
        entry.update(status="migrated", backup=str(backup), valid=True)
        fixed += 1
    except OSError as exc:
        entry.update(status="migration_failed", backup=str(backup), valid=False, error=str(exc))
```

`migration_failed` 必须携带 `backup` 路径，用户可据此恢复。

## D4. status 支持 --dir + 文案修正

- `cli.py`：`sk_status.add_argument("--dir", help="自定义 skills 目录")`；`_target_dirs` 已用 `getattr(args, "dir", None)`，零改动生效。
- `capabilities.py`：`status` 声明 `args: [{"name": "--dir", "help": "自定义目录"}]`（契约测试逐参数比对，必须同步）。
- `install --dir` 帮助文案改为 `自定义 skills 目录(默认 ~/.qoder/skills 与 ~/.qoderwork/skills)`。

## D5. 源标识含工作区脏标记

`_get_source_info` 追加一次 `git status --porcelain`（timeout=5）：非空输出 → `source_dirty: true`；失败/超时 → `None`（未知）。`update`/`status` 顶层透传。用途：声明"对齐到 commit X"时如实说明工作区是否有未提交改动，标识才可证伪。

## D6. 测试策略

`test_skill_management.py` 新增（沿用现有 monkeypatch `_SEEK_ROOT/_SKILL_DIRS/_SKILL_FILE` 模式，新增保存/恢复 `skill.__version__`）：

1. `test_update_detects_cli_version_ref_mismatch`：frontmatter `cli_version_ref: 9.9.9`，`skill.__version__ = "0.4.0"` → `version_consistency.consistent is False`，message 含告警，命令仍 `status=ok`。
2. `test_update_silent_when_versions_consistent`：`skill.__version__` 与 ref 相同 → `consistent is True`，message 无告警词。
3. `test_update_isolates_per_directory_failures`：dir1 为 foreign（可修复）、dir2 父目录 0o500 → dir1 entry 为 `fixed` 且链接已改写，dir2 entry 为 `error`，命令不抛异常、results 含两条。
4. `test_update_labels_migration_failed_with_backup_path`：legacy 目录 chmod 0o500（内容可读不可删）→ `status=migration_failed` 且 `backup` 文件存在。
5. `test_status_accepts_dir_argument`：`cmd_skill_status(args(directory))` 只检查指定目录。
6. `test_source_info_reports_dirty_working_tree`：临时 git 仓库提交后改脏 → `source_dirty is True`；干净时 `False`。

capabilities 契约测试因声明同步而保持全绿；全量 `python -m unittest discover cli/tests` 回归。

## D7. 兼容性与边界

- 既有合法调用行为不变：`up_to_date` 判定逻辑、退出码、JSON 结构均为增量字段。
- `version_consistency.consistent=None`（frontmatter 未声明）不告警，兼容老格式。
- 非 git 源目录：`commit=None`、`source_dirty=None`，行为与现状一致。
