"""seek 运行时路径解析。

设置 ``SEEK_HOME`` 可将 seek 自有的配置、会话和日志隔离到指定目录；
未设置时保持 ``~/.seek`` 的历史默认路径。
"""

import os
from pathlib import Path


def seek_home() -> Path:
    """返回 seek 可变运行时状态根目录。

    Returns:
        ``SEEK_HOME`` 指向的展开路径；变量未设置或为空时返回 ``~/.seek``。
    """
    override = os.environ.get("SEEK_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".seek"


def seek_home_source() -> str:
    """返回当前 seek home 的配置来源。"""
    return "SEEK_HOME" if os.environ.get("SEEK_HOME", "").strip() else "default"


def seek_path(*parts: str) -> Path:
    """返回 seek home 下的路径。"""
    return seek_home().joinpath(*parts)
