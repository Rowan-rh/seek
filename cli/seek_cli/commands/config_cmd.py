"""统一配置管理命令 — seek config

show / get / set / unset / path，配置统一存放在 ~/.seek/config/seek.json。
读取优先级（各集成一致）：环境变量 > seek.json > 各自旧文件 > 默认值。
"""

import os
from pathlib import Path

from seek_cli import settings
from seek_cli import config as seek_config
from seek_cli.output import success, error
from seek_cli.plugins import get_provider
from seek_cli.paths import seek_home, seek_home_source


_alibaba = get_provider("alibaba")
expert_client = _alibaba.service("expert")
roar_client = _alibaba.service("roar")

# show 时各配置项的环境变量与旧文件来源（用于标注生效来源）
_ENV_KEYS = {
    "sls.access_key_id": "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "sls.access_key_secret": "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "sls.security_token": "ALIBABA_CLOUD_SECURITY_TOKEN",
    "hosts.expert": "QT_EXPERT_HOST",
    "hosts.roar": "ROAR_HOST",
    "trace.topologyFile": "SEEK_TOPOLOGY_FILE",
    "options.quiet_warnings": "SEEK_QUIET_WARNINGS",
}
_LEGACY_FILES = {
    "sls.access_key_id": seek_home() / "credentials.json",
    "sls.access_key_secret": seek_home() / "credentials.json",
    "sls.security_token": seek_home() / "credentials.json",
    "hosts.expert": seek_home() / "config" / "expert.json",
    "hosts.roar": seek_home() / "config" / "roar.json",
    "trace.topologyFile": seek_home() / "config" / "trace.json",
}


def _effective(key: str) -> dict:
    """解析单个配置项的生效值与来源（判定逻辑与各集成实际读取链保持一致）"""
    entry = {
        "key": key,
        "help": settings.KEY_SCHEMA[key]["help"],
        "value": None,
        "source": "unset",
    }
    secret = settings.KEY_SCHEMA[key]["secret"]

    if key in ("sls.access_key_id", "sls.access_key_secret", "sls.security_token"):
        entry.update(_effective_sls_key(key))
    elif key == "options.quiet_warnings":
        # 与 settings.quiet_warnings() 一致：env 只认 "1"
        if os.environ.get("SEEK_QUIET_WARNINGS") == "1":
            entry["value"] = True
            entry["source"] = "env:SEEK_QUIET_WARNINGS"
        else:
            val = settings.get_setting(key)
            if val is not None:
                entry["value"] = settings.as_bool(val)
                entry["source"] = str(settings.SETTINGS_FILE)
    else:
        # 单键 fallback 链：env > seek.json > legacy 文件存在性
        env_name = _ENV_KEYS.get(key)
        env_val = os.environ.get(env_name) if env_name else None
        if env_val:
            if key == "trace.topologyFile" and not Path(env_val).exists():
                entry["value"] = str(seek_config.get_topology_file())
                entry["source"] = "fallback:invalid-env"
            else:
                entry["value"] = env_val
                entry["source"] = f"env:{env_name}"
        else:
            val = settings.get_setting(key)
            if val is not None:
                if key == "trace.topologyFile" and not Path(val).exists():
                    entry["value"] = str(seek_config.get_topology_file())
                    entry["source"] = "fallback:invalid-seek.json"
                else:
                    entry["value"] = val
                    entry["source"] = str(settings.SETTINGS_FILE)
            else:
                legacy = _LEGACY_FILES.get(key)
                if legacy and legacy.exists():
                    entry["source"] = f"legacy:{legacy}"
                elif key == "hosts.expert":
                    entry["value"] = expert_client.DEFAULT_HOST
                    entry["source"] = "default:built-in"
                elif key == "hosts.roar":
                    entry["value"] = roar_client.DEFAULT_HOST
                    entry["source"] = "default:built-in"
                elif key == "trace.topologyFile":
                    topology = seek_config.get_topology_file()
                    entry["value"] = str(topology)
                    entry["source"] = (
                        "default:candidate" if topology.exists()
                        else "default:candidate-missing"
                    )

    if secret and entry["value"] is not None:
        entry["value"] = settings.mask_secret(entry["value"])
    return entry


def _effective_sls_key(key: str) -> dict:
    """SLS 凭据三键的来源判定：与 sls_client._get_credentials 一致，ak+sk 必须成对才生效"""
    env_ak = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or ""
    env_sk = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or ""
    cfg_ak = settings.get_setting("sls.access_key_id")
    cfg_sk = settings.get_setting("sls.access_key_secret")

    env_names = {
        "sls.access_key_id": "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "sls.access_key_secret": "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "sls.security_token": "ALIBABA_CLOUD_SECURITY_TOKEN",
    }
    if env_ak and env_sk:
        value = os.environ.get(env_names[key]) or None
        return {"value": value, "source": f"env:{env_names[key]}"}
    if cfg_ak and cfg_sk:
        value = settings.get_setting(key)
        return {"value": value, "source": str(settings.SETTINGS_FILE)}

    # 未成对时的部分配置提示（不生效，仅提示）
    partial_env = bool(env_ak or env_sk)
    partial_cfg = bool(cfg_ak or cfg_sk)
    if key in ("sls.access_key_id", "sls.access_key_secret"):
        if partial_env:
            return {"value": None, "source": "incomplete:env(需 ak+sk 成对才生效)"}
        if partial_cfg:
            return {"value": None,
                    "source": f"incomplete:{settings.SETTINGS_FILE}(需 ak+sk 成对才生效)"}
    # 整体回退到 credentials.json / 阿里云 CLI 配置
    legacy = _LEGACY_FILES.get(key)
    if legacy and legacy.exists():
        return {"value": None, "source": f"legacy:{legacy}"}
    return {"value": None, "source": "unset"}


def cmd_config_show(args) -> dict:
    """聚合展示全部配置项的生效值与来源"""
    items = [_effective(k) for k in settings.KEY_SCHEMA]
    # incomplete（ak/sk 未成对）不计入已生效
    configured = sum(1 for i in items
                     if i["source"] not in ("unset",)
                     and not i["source"].startswith("incomplete"))
    return success({
        "settings_file": str(settings.SETTINGS_FILE),
        "settings_file_exists": settings.SETTINGS_FILE.exists(),
        "items": items,
        "configured": configured,
        "total": len(items),
    }, message=f"配置总览: {configured}/{len(items)} 项已生效（secret 已脱敏）")


def cmd_config_get(args) -> dict:
    """读取单个配置项"""
    key = args.key
    if key not in settings.KEY_SCHEMA:
        return error(
            f"未知配置键: {key}。可用键: {', '.join(settings.KEY_SCHEMA)}",
            code="BAD_CONFIG_KEY")
    entry = _effective(key)
    return success(entry, message=f"{key}: {entry['value'] if entry['value'] is not None else '(未设置)'}")


def cmd_config_set(args) -> dict:
    """写入配置项到 seek.json"""
    try:
        cfg = settings.set_setting(args.key, args.value)
    except KeyError as e:
        return error(e.args[0] if e.args else str(e), code="BAD_CONFIG_KEY")
    masked = settings.mask_secret(args.value) if settings.KEY_SCHEMA[args.key]["secret"] else args.value
    return success(
        {"key": args.key, "value": masked, "file": str(settings.SETTINGS_FILE)},
        message=f"已写入 {args.key}={masked} 到 {settings.SETTINGS_FILE}")


def cmd_config_unset(args) -> dict:
    """删除配置项（回退到环境变量/旧文件/默认值）"""
    if args.key not in settings.KEY_SCHEMA:
        return error(
            f"未知配置键: {args.key}。可用键: {', '.join(settings.KEY_SCHEMA)}",
            code="BAD_CONFIG_KEY")
    removed = settings.unset_setting(args.key)
    return success({"key": args.key, "removed": removed},
                   message=f"{'已删除' if removed else '未设置，无需删除'} {args.key}")


def cmd_config_path(args) -> dict:
    """输出配置目录与各配置文件存在状态"""
    home_seek = seek_home()
    files = {
        "settings": settings.SETTINGS_FILE,
        "projects": home_seek / "config" / "projects.json",
        "credentials_legacy": home_seek / "credentials.json",
        "expert_legacy": home_seek / "config" / "expert.json",
        "roar_legacy": home_seek / "config" / "roar.json",
        "trace_legacy": home_seek / "config" / "trace.json",
        "sessions_dir": home_seek / "sessions",
        "logs_dir": home_seek / "logs",
    }
    report = {name: {"path": str(p), "exists": p.exists()}
              for name, p in files.items()}
    return success({
        "home": str(home_seek),
        "home_source": seek_home_source(),
        "files": report,
    }, message=f"配置根目录: {home_seek}")
