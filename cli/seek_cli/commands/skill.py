"""Skill 管理命令 — 安装/更新/检查/卸载 seek skill 到 Qoder skills 目录"""

import os
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

from seek_cli import __version__
from seek_cli.output import success, error

_SEEK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SKILL_FILE = _SEEK_ROOT / "SKILL.md"
_SKILL_DIRS = [
    Path.home() / ".qoder" / "skills",
    Path.home() / ".qoderwork" / "skills",
]
_SKILL_NAME = "seek"


def _target_dirs(args) -> list:
    """Resolve the requested installation directories."""
    return [Path(args.dir).expanduser()] if getattr(args, "dir", None) else list(_SKILL_DIRS)


def _resolved_link_target(link: Path) -> Path:
    """Resolve an absolute or relative symlink target relative to its link."""
    raw_target = Path(os.readlink(link))
    if not raw_target.is_absolute():
        raw_target = link.parent / raw_target
    return raw_target.resolve(strict=False)


def _link_status(link: Path) -> str:
    """Classify an installation path without following a dangling link."""
    if link.is_symlink():
        try:
            target = _resolved_link_target(link)
        except OSError:
            return "broken"
        if not (target / "SKILL.md").is_file():
            return "broken"
        return "up_to_date" if target == _SEEK_ROOT.resolve() else "foreign"
    if link.is_dir():
        return "directory"
    if link.exists():
        return "conflict"
    return "not_found"


def _frontmatter_value(name: str) -> str:
    """Read a simple scalar from SKILL.md frontmatter."""
    try:
        lines = _SKILL_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].split("#", 1)[0].strip().strip("\"'")
    return ""


def get_source_info() -> dict:
    """Read source versions, mtime, git commit and worktree state for status/update output."""
    info = {
        "cli_version": __version__,
        "skill_doc_version": _frontmatter_value("skill_doc_version"),
        "cli_version_ref": _frontmatter_value("cli_version_ref"),
        "skill_mtime": None,
        "skill_mtime_iso": None,
        "source_dirty": None,
    }
    if _SKILL_FILE.exists():
        mtime = _SKILL_FILE.stat().st_mtime
        info["skill_mtime"] = mtime
        info["skill_mtime_iso"] = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_SEEK_ROOT), capture_output=True, text=True, timeout=5,
        )
        info["commit"] = result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        info["commit"] = None
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(_SEEK_ROOT), capture_output=True, text=True, timeout=5,
        )
        info["source_dirty"] = bool(dirty.stdout.strip()) if dirty.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return info


def version_consistency(source_info: dict) -> dict:
    """Cross-check declared cli_version_ref against the running CLI version."""
    declared = source_info.get("cli_version_ref") or None
    actual = source_info["cli_version"]
    return {
        "declared_cli_version": declared,
        "actual_cli_version": actual,
        "consistent": (declared == actual) if declared else None,
    }


# 兼容旧测试和调用方；新代码使用公共函数。
_get_source_info = get_source_info
_version_consistency = version_consistency


def _mismatch_warning(consistency: dict) -> str:
    """Build the version-drift warning text, empty when consistent or unknown."""
    if consistency["consistent"] is False:
        return (f"；版本声明不匹配: cli_version_ref={consistency['declared_cli_version']}"
                f" ≠ 实际 {consistency['actual_cli_version']}")
    return ""


def _version_tag(source_info: dict) -> str:
    tag = f"skill-doc v{source_info.get('skill_doc_version') or '?'} / cli v{source_info['cli_version']}"
    if source_info.get("commit"):
        tag += f" ({source_info['commit']})"
    return tag


def _backup_directory(directory: Path) -> Path:
    """Compress a legacy directory beside its parent before migration."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = directory.parent / f"{directory.name}.backup-{timestamp}.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(directory, arcname=directory.name)
    return backup


def _install_link(link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(_SEEK_ROOT), str(link))


def cmd_skill_install(args) -> dict:
    """Install seek skill links into the selected skill directories."""
    if not _SKILL_FILE.exists():
        return error(f"SKILL.md not found at {_SKILL_FILE}", code="NOT_FOUND")
    results = []
    for target_dir in _target_dirs(args):
        link = target_dir / _SKILL_NAME
        status = _link_status(link)
        if status == "up_to_date":
            result = {"dir": str(target_dir), "link": str(link), "status": "already_installed"}
        elif status == "directory":
            result = {"dir": str(target_dir), "link": str(link), "status": "exists_as_directory",
                      "note": "已存在为目录，未覆盖；请使用 seek skill update 迁移并保留压缩备份"}
        elif status == "conflict":
            result = {"dir": str(target_dir), "link": str(link), "status": "conflict",
                      "note": "目标路径已存在且不是符号链接，未覆盖"}
        else:
            if link.is_symlink():
                link.unlink()
            _install_link(link)
            result = {"dir": str(target_dir), "link": str(link), "status": "installed"}
        results.append(result)
    installed = sum(r["status"] == "installed" for r in results)
    return success({"skill": _SKILL_NAME, "target": str(_SEEK_ROOT), "results": results,
                    "installed": installed}, message=f"skill 安装完成: {installed} 处新安装")


def cmd_skill_update(args) -> dict:
    """Update all selected installations, backing up legacy directories first."""
    if not _SKILL_FILE.exists():
        return error(f"SKILL.md not found at {_SKILL_FILE}", code="NOT_FOUND")
    source_info = get_source_info()
    consistency = version_consistency(source_info)
    results = []
    fixed = 0
    for target_dir in _target_dirs(args):
        link = target_dir / _SKILL_NAME
        status = _link_status(link)
        entry = {"dir": str(target_dir), "link": str(link), "status": status,
                 "skill_doc_version": source_info.get("skill_doc_version"),
                 "cli_version": source_info["cli_version"],
                 "source_commit": source_info.get("commit"),
                 "source_skill_mtime": source_info.get("skill_mtime_iso")}
        if status == "up_to_date":
            entry["note"] = f"已对齐到 {_version_tag(source_info)}"
            if consistency["consistent"] is False:
                entry["note"] += (f"（声明 cli_version_ref {consistency['declared_cli_version']}"
                                  f" ≠ 实际 {consistency['actual_cli_version']}）")
        elif status == "directory":
            try:
                backup = _backup_directory(link)
            except (OSError, tarfile.TarError) as exc:
                entry.update(status="backup_failed", valid=False, error=str(exc))
            else:
                try:
                    shutil.rmtree(link)
                    _install_link(link)
                    entry.update(status="migrated", backup=str(backup), valid=True)
                    entry["note"] = f"已压缩备份后迁移到 {_version_tag(source_info)}"
                    fixed += 1
                except OSError as exc:
                    entry.update(status="migration_failed", backup=str(backup),
                                 valid=False, error=str(exc))
        elif status in ("broken", "foreign"):
            old_target = None
            try:
                if link.is_symlink():
                    try:
                        old_target = str(_resolved_link_target(link))
                    except OSError:
                        pass
                    link.unlink()
                _install_link(link)
                entry.update(status="fixed", previous_target=old_target, valid=True)
                fixed += 1
            except OSError as exc:
                entry.update(status="error", valid=False, error=str(exc))
        elif status == "not_found":
            try:
                _install_link(link)
                entry.update(status="installed", valid=True)
                fixed += 1
            except OSError as exc:
                entry.update(status="error", valid=False, error=str(exc))
        else:
            entry.update(status="conflict", valid=False,
                         error="目标路径已存在且不是目录或符号链接")
        if "valid" not in entry:
            entry["valid"] = _link_status(link) == "up_to_date"
        results.append(entry)
    return success({"skill": _SKILL_NAME, "source": str(_SEEK_ROOT),
                    "skill_doc_version": source_info.get("skill_doc_version"),
                    "cli_version": source_info["cli_version"],
                    "source_commit": source_info.get("commit"),
                    "source_skill_mtime": source_info.get("skill_mtime_iso"),
                    "source_dirty": source_info.get("source_dirty"),
                    "version_consistency": consistency,
                    "results": results, "updated": fixed},
                    message=f"skill 更新完成: {fixed} 处修复/安装"
                            + _mismatch_warning(consistency))


def cmd_skill_status(args) -> dict:
    """Check all selected skill installation locations."""
    source_info = get_source_info()
    consistency = version_consistency(source_info)
    locations = []
    for target_dir in _target_dirs(args):
        link = target_dir / _SKILL_NAME
        status = _link_status(link)
        item = {"dir": str(target_dir), "link": str(link), "status": status,
                "type": "symlink" if link.is_symlink() else status,
                "valid": status == "up_to_date"}
        if link.is_symlink():
            item["target"] = str(_resolved_link_target(link))
        locations.append(item)
    installed = any(item["valid"] for item in locations)
    return success({"skill": _SKILL_NAME, "source": str(_SKILL_FILE),
                    "source_exists": _SKILL_FILE.exists(), "skill_doc_version": source_info.get("skill_doc_version"),
                    "cli_version": source_info["cli_version"],
                    "source_commit": source_info.get("commit"),
                    "source_dirty": source_info.get("source_dirty"),
                    "version_consistency": consistency,
                    "installed": installed,
                    "locations": locations},
                    message=f"skill {'已安装' if installed else '未安装'}"
                            + _mismatch_warning(consistency))


def cmd_skill_uninstall(args) -> dict:
    """Uninstall links from all selected directories without deleting source files."""
    results = []
    for target_dir in _target_dirs(args):
        link = target_dir / _SKILL_NAME
        status = _link_status(link)
        if link.is_symlink():
            link.unlink()
            results.append({"dir": str(target_dir), "link": str(link), "removed": True, "status": status})
        elif status == "not_found":
            results.append({"dir": str(target_dir), "link": str(link), "removed": False, "status": status})
        else:
            results.append({"dir": str(target_dir), "link": str(link), "removed": False, "status": status,
                            "note": "不是符号链接，未删除"})
    removed = sum(item["removed"] for item in results)
    return success({"removed": removed, "results": results}, message=f"skill 已卸载: {removed} 处")
