# Proposal: fix-skill-update-consistency

## Why

`seek skill update` 的本意是让安装点与源码对齐并如实报告，但 2026-09-01 的临时复验脚本（跑完即删）确认了 4 个真实缺陷，其中两个会造成状态破坏或信息丢失：

1. **假对齐（最严重）**：把 `cli_version_ref` 改成荒谬值 `9.9.9`，`update` 仍返回 `status=up_to_date / valid=true / updated=0`，note 写"已对齐"。根因：`_link_status` 只比较符号链接目标是否等于仓库根，结果条目里的版本字段全部是 `_get_source_info()` 的源侧回显，不读安装点、不做交叉核对。`cli_version_ref` 全仓无任何代码读取，是零校验的纯声明。真实漂移已发生：`8a62f6b` 将 `cli_version_ref` 提到 0.5.0，而 `__version__` 仍是 0.4.0，命令静默放行。
2. **中途异常不隔离**：`broken`/`foreign`/`not_found` 三个修复分支的 `unlink()+_install_link()` 没有 try/except。复验：第一个目录已被静默改写指向新源后，第二个目录 `PermissionError` 抛出，累积的 `results` 一条都没输出。
3. **迁移失败误标**：备份、删目录、建链三步被一个 except 合并捕获。复验：备份 tar.gz 已成功生成，rmtree 失败却标 `backup_failed` 且不回显 backup 路径。
4. **`status` 缺 `--dir`**：install/update/uninstall 都有 `--dir`，唯独 status 没有（`seek skill status --dir X` 退出码 2），自定义目录装完无法复查；`install --dir` 帮助文案声称默认仅 `~/.qoder/skills`，实际默认是两个目录。

次要：`source_commit` 取 `git rev-parse --short HEAD`，无 dirty 标记——工作区改脏后 commit 号不变，对齐标识不代表实际内容。

## What Changes

- **版本一致性校验**：`update`/`status` 比较 frontmatter 的 `cli_version_ref` 与实际 `__version__`，不匹配时输出 `version_consistency` 结构并在 message 追加告警；命令仍为 `status=ok`、退出码 0（警告而非失败）。
- **逐目录失败隔离**：修复类分支逐目录 try/except，单目录失败标 `status=error` 并继续，已完成结果不丢。
- **迁移分阶段标注**：备份失败标 `backup_failed`；备份成功但删除/建链失败标 `migration_failed` 并回显已生成的 `backup` 路径。
- **`status` 补 `--dir`**：与 install/update/uninstall 语义一致；同步更新 capabilities 声明与 `install --dir` 帮助文案。
- **源标识如实化**：`_get_source_info` 增加 `source_dirty`（`git status --porcelain` 非空）。

## Capabilities

### New Capabilities
- `skill-install-consistency`: skill 安装/更新命令的对齐判定必须如实可证伪——版本声明交叉校验、逐目录失败隔离、迁移阶段准确标注、状态检查能力对称、源标识含工作区脏标记。

### Modified Capabilities
（无）

## Impact

- **代码**：`cli/seek_cli/commands/skill.py`（核心修复）、`cli/seek_cli/cli.py`（status 加 `--dir`、install 帮助文案）、`cli/seek_cli/commands/capabilities.py`（status args 声明）。
- **测试**：`cli/tests/test_skill_management.py` 新增 6 项回归（漂移检出/一致静默、异常隔离、迁移分阶段、status --dir、dirty 标记）；capabilities 契约测试同步。
- **文档**：`references/command-reference.md`（如含 skill 命令条目）。
- 不改 `SKILL.md` 的版本值：漂移本身（0.5.0 vs 0.4.0）属发布决策，本变更只让命令如实报告。
