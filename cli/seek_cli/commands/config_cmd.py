"""seek 核心配置命令。Provider 配置由插件自行管理。"""

import os

from seek_cli import settings
from seek_cli.output import success, error
from seek_cli.paths import seek_home, seek_home_source


def _effective(key: str) -> dict:
    if key not in settings.KEY_SCHEMA:
        raise KeyError(key)
    value = settings.get_setting(key)
    if key == "options.quiet_warnings" and settings.quiet_warnings():
        value = True
        source = "env:SEEK_QUIET_WARNINGS" if os.environ.get("SEEK_QUIET_WARNINGS") == "1" else str(settings.SETTINGS_FILE)
    elif value is None:
        source = "default"
        if key == "options.perf_log":
            value = True
    else:
        source = str(settings.SETTINGS_FILE)
    return {"key": key, "help": settings.KEY_SCHEMA[key]["help"],
            "value": value, "source": source}


def cmd_config_show(args) -> dict:
    items = [_effective(key) for key in settings.KEY_SCHEMA]
    configured = sum(1 for item in items if item["source"] != "default")
    return success({
        "settings_file": str(settings.SETTINGS_FILE),
        "settings_file_exists": settings.SETTINGS_FILE.exists(),
        "items": items,
        "configured": configured,
        "total": len(items),
        "provider_configuration": "managed by installed plugins",
    }, message=f"配置总览: {configured}/{len(items)} 项已设置")


def cmd_config_get(args) -> dict:
    if args.key not in settings.KEY_SCHEMA:
        return error(f"未知配置键: {args.key}。可用键: {', '.join(settings.KEY_SCHEMA)}", code="BAD_CONFIG_KEY")
    item = _effective(args.key)
    return success(item, message=f"{args.key}: {item['value']}")


def cmd_config_set(args) -> dict:
    try:
        settings.set_setting(args.key, args.value)
    except KeyError as exc:
        return error(str(exc), code="BAD_CONFIG_KEY")
    return success({"key": args.key, "value": settings.get_setting(args.key),
                    "file": str(settings.SETTINGS_FILE)},
                   message=f"已写入 {args.key}")


def cmd_config_unset(args) -> dict:
    try:
        removed = settings.unset_setting(args.key)
    except KeyError as exc:
        return error(str(exc), code="BAD_CONFIG_KEY")
    return success({"key": args.key, "removed": removed},
                   message=f"{'已删除' if removed else '未设置，无需删除'} {args.key}")


def cmd_config_path(args) -> dict:
    home = seek_home()
    files = {
        "settings": settings.SETTINGS_FILE,
        "projects": home / "config" / "projects.json",
        "sessions_dir": home / "sessions",
        "logs_dir": home / "logs",
    }
    return success({
        "home": str(home),
        "home_source": seek_home_source(),
        "files": {name: {"path": str(path), "exists": path.exists()}
                  for name, path in files.items()},
    }, message=f"配置根目录: {home}")
