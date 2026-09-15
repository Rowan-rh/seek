#!/usr/bin/env python3
"""seek-cli — AI agent 排查编排 CLI 工具"""

import ast
from pathlib import Path

from setuptools import find_packages, setup


_ROOT = Path(__file__).parent


def read_version() -> str:
    """从 seek_cli/__init__.py 读取唯一运行时版本源。"""
    source = (_ROOT / "seek_cli" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    raise RuntimeError("__version__ not found in seek_cli/__init__.py")


setup(
    name="seek-cli",
    version=read_version(),
    description="AI agent troubleshooting orchestration CLI — for agent use, not humans",
    author="seek",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=[
        "aliyun-log-python-sdk>=0.9.0",
        "requests>=2.20.0",
    ],
    extras_require={
        # 本地直连数据库（seek db --conn），日常/预发环境可选能力
        "mysql": ["PyMySQL>=1.1"],
    },
    entry_points={
        "console_scripts": [
            "seek=seek_cli.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "seek_cli": [
            "resources/config/*.json",
            "resources/chains/*.json",
            "resources/chains/templates/*.md",
        ],
    },
)
