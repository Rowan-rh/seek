"""版本命令 — 输出当前版本和变更记录"""

from seek_cli import __version__, CHANGELOG
from seek_cli.output import success


def cmd_version(args) -> dict:
    """输出当前版本和变更记录"""
    return success({
        "version": __version__,
        "changelog": CHANGELOG,
    }, message=f"seek CLI v{__version__}")
