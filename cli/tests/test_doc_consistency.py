"""文档与运行时权威的一致性守护。

复制事实靠人工同步已经腐化过多次：TROUBLESHOOTING 写"4 条链路"、README 写
"10 个项目"，而实际分别是 7 条和 15 个。本模块把可派生的事实绑定到运行时权威，
并禁止文档继续硬编码会漂移的计数。

运行时权威是 setup.py 唯一打包的副本：

- 链路定义 ``cli/seek_cli/resources/chains/default.json``
- 种子项目配置 ``cli/seek_cli/resources/config/projects.json``

``cli/chains/`` 与 ``cli/config/`` 是人类编辑镜像，代码不读取（模板镜像的同款守护
已在 test_report_templates.py）。
"""

import argparse
import json
import re
import sys
import unittest
from pathlib import Path

_CLI_ROOT = Path(__file__).resolve().parents[1]
if str(_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLI_ROOT))

_REPO_ROOT = _CLI_ROOT.parent

_RUNTIME_CHAINS = _CLI_ROOT / "seek_cli" / "resources" / "chains" / "default.json"
_RUNTIME_PROJECTS = _CLI_ROOT / "seek_cli" / "resources" / "config" / "projects.json"

# (人类编辑镜像, 运行时权威)
_MIRRORS = (
    (_CLI_ROOT / "chains" / "default.json", _RUNTIME_CHAINS),
    (_CLI_ROOT / "config" / "projects.json", _RUNTIME_PROJECTS),
)

_DOCS = (
    "README.md",
    "AGENT.md",
    "SKILL.md",
    "cli/README.md",
    "cli/TROUBLESHOOTING.md",
    "references/SOP-seek-investigation.md",
    "references/command-reference.md",
    "references/emergency-response-patterns.md",
    "references/evidence-and-boundaries.md",
    "references/investigation-patterns.md",
)

# 会随代码漂移的计数：文档必须指向权威命令，不能写死数字
_FORBIDDEN_COUNTS = (
    (re.compile(r"\d+\s*条链路"), "seek chain list"),
    (re.compile(r"\d+\s*个(?:\s*QT)?\s*项目"), "seek project list"),
    (re.compile(r"\d+\s*个(?:子命令|命令组|独立命令)"), "seek capabilities"),
)

_MD_LINK = re.compile(r"\]\(([^)\s]+?\.md)\)")
_CHAT_ID = re.compile(r"cid[A-Za-z0-9+/]{8,}={0,2}")


def _load_chains() -> dict:
    """读取运行时链路定义。"""
    return json.loads(_RUNTIME_CHAINS.read_text(encoding="utf-8"))["chains"]


def _first_step_inputs(chain: dict) -> list:
    """镜像 chain.first_step_external_inputs 的口径，只读运行时文件不引入用户覆盖。"""
    steps = chain.get("steps", [])
    produced = {output for step in steps for output in step.get("outputs", [])}
    return [key for key in steps[0].get("requiredInputs", []) if key not in produced]


def _read(doc: str) -> str:
    return (_REPO_ROOT / doc).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """取出指定小节正文，到下一个同级或更高级标题为止。"""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.find(heading)
    if start < 0:
        raise AssertionError(f"未找到小节标题: {heading}")
    body = text[start + len(heading):]
    end = re.search(rf"^#{{1,{level}}} ", body, re.MULTILINE)
    return body[:end.start()] if end else body


def _is_separator_row(cells: list) -> bool:
    """判断是否为 markdown 表格的 |---|---| 分隔行。"""
    return all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells)


def _table_rows(text: str, heading: str) -> list:
    """取出指定小节下第一张 markdown 表的数据行（已去表头与分隔行）。"""
    rows = []
    for line in _section(text, heading).splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
            continue
        if rows:
            break
    body = [cells for cells in rows if not _is_separator_row(cells)]
    if len(body) < 2:
        raise AssertionError(f"小节 {heading} 下未找到数据表")
    return body[1:]


class MirrorConsistencyTest(unittest.TestCase):
    def test_edit_mirrors_match_runtime_resources(self):
        for mirror, runtime in _MIRRORS:
            with self.subTest(mirror=str(mirror.relative_to(_REPO_ROOT))):
                self.assertTrue(mirror.is_file(), f"缺少编辑镜像 {mirror}")
                self.assertEqual(
                    mirror.read_bytes(), runtime.read_bytes(),
                    f"{mirror.relative_to(_REPO_ROOT)} 与运行时权威 "
                    f"{runtime.relative_to(_REPO_ROOT)} 不一致；setup.py 只打包 "
                    "resources/ 下的副本，改镜像不改运行时副本不会生效",
                )


class HardcodedCountTest(unittest.TestCase):
    def test_docs_do_not_hardcode_catalog_counts(self):
        violations = []
        for doc in _DOCS:
            text = _read(doc)
            for pattern, authority in _FORBIDDEN_COUNTS:
                for match in pattern.finditer(text):
                    line = text[:match.start()].count("\n") + 1
                    violations.append(
                        f"{doc}:{line} 硬编码 '{match.group(0)}'，应指向 `{authority}`"
                    )
        self.assertEqual([], violations, "以下计数会随代码漂移，已腐化过多次")


class ChainTableTest(unittest.TestCase):
    def test_skill_chain_table_matches_definition(self):
        chains = _load_chains()
        rows = _table_rows(_read("SKILL.md"), "### 内置链路")
        documented = {cells[0].strip("`"): cells for cells in rows}
        self.assertEqual(set(documented), set(chains),
                         "SKILL.md 内置链路表与链路定义不一致")
        for name, cells in documented.items():
            with self.subTest(chain=name):
                # 步骤列以 → 串联步骤名，箭头数 + 1 即步骤数
                self.assertEqual(cells[3].count("→") + 1, len(chains[name]["steps"]),
                                 f"SKILL.md 中 {name} 的步骤数与定义不符")
                for key in _first_step_inputs(chains[name]):
                    self.assertIn(key, cells[2],
                                  f"SKILL.md 中 {name} 的首步输入列缺少 {key}")

    def test_sop_chain_table_matches_definition(self):
        from seek_cli.chain import _PROBLEM_DESCRIPTION_INPUTS

        chains = _load_chains()
        rows = _table_rows(
            _read("references/SOP-seek-investigation.md"), "### 2.1 链路清单"
        )
        documented = {cells[0].strip("`"): cells for cells in rows}
        self.assertEqual(set(documented), set(chains),
                         "SOP 链路清单与链路定义不一致")
        for name, cells in documented.items():
            chain = chains[name]
            inputs = _first_step_inputs(chain)
            with self.subTest(chain=name):
                self.assertEqual(int(cells[4]), len(chain["steps"]), "步骤数不符")
                self.assertEqual(cells[5], chain.get("reportTemplate") or "generic.md",
                                 "报告模板不符")
                self.assertIn(cells[2].strip("`"), inputs, "首步输入键不符")
                expected = "--problem" if cells[2].strip("`") in _PROBLEM_DESCRIPTION_INPUTS else "--context"
                self.assertIn(expected, cells[3],
                              f"{name} 的输入来源应为 {expected}")


class LinkResolutionTest(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        broken = []
        for doc in _DOCS:
            path = _REPO_ROOT / doc
            for match in _MD_LINK.finditer(path.read_text(encoding="utf-8")):
                target = match.group(1)
                if not (path.parent / target).resolve().is_file():
                    broken.append(f"{doc} -> {target}")
        self.assertEqual([], broken, "以下相对链接指向不存在的文件")


class CheatsheetCoverageTest(unittest.TestCase):
    def test_skill_chain_cheatsheet_lists_every_subcommand(self):
        from seek_cli.cli import _build_parser

        top = next(action for action in _build_parser()._actions
                   if isinstance(action, argparse._SubParsersAction))
        nested = next(action for action in top.choices["chain"]._actions
                      if isinstance(action, argparse._SubParsersAction))
        section = _section(_read("SKILL.md"), "### 排查链路（核心）")
        missing = sorted(name for name in nested.choices
                         if f"chain {name}" not in section)
        self.assertEqual([], missing,
                         f"SKILL.md 命令速查缺少 chain 子命令: {missing}")


class EntryPointHygieneTest(unittest.TestCase):
    def test_skill_entry_has_no_chat_identifiers(self):
        hits = _CHAT_ID.findall(_read("SKILL.md"))
        self.assertEqual([], hits,
                         "SKILL.md 自身规则禁止在入口文档复制具体群 ID；"
                         "案例应下沉到 references/investigation-patterns.md 并去标识化")


def _has_enabled_sls(project: dict) -> bool:
    """判断项目配置里是否存在 enabled 的 SLS platform。"""
    for env_config in (project.get("environments") or {}).values():
        if not isinstance(env_config, dict):
            continue
        for platform in env_config.get("platforms") or []:
            if (isinstance(platform, dict)
                    and platform.get("type") == "sls"
                    and platform.get("enabled")):
                return True
    return False


class EvidenceDeclarationTest(unittest.TestCase):
    def test_external_tool_steps_require_evidence(self):
        chains = _load_chains()
        missing = []
        for chain_name, chain in chains.items():
            for step in chain["steps"]:
                tools = step.get("tools", [])
                has_external_tool = any(tool.strip() != "chain context" for tool in tools)
                if has_external_tool and not step.get("evidenceRequired"):
                    missing.append(f"{chain_name}/{step['name']}")
        self.assertEqual([], missing, f"外部取证步骤缺少 evidenceRequired: {missing}")


class ChainToolHintResolutionTest(unittest.TestCase):
    """链路 tools 里的项目级 SLS 提示必须真能查到东西。

    ``notification`` step4 曾提示 ``seek sls query notice-service --env <env>``，
    而 ``notice-service`` 的 ``environments`` 为空，agent 照提示执行必然拿到
    ``SLS_QUERY_ERROR: environment not configured``。工具提示是 agent 的唯一
    行动依据，指向不存在的取证通道等同于把排查引向死路。

    只校验项目级查询（``sls query/logs/config <项目名>``）：项目名要求以小写
    字母开头，因此 ``--endpoint`` 等选项与 ``<project>`` 占位符不会误命中；
    直查模式由作业者自带坐标，不由种子配置决定，不在守护范围内。
    """

    _SLS_PROJECT_HINT = re.compile(
        r"seek\s+sls\s+(?:query|logs|config)\s+([a-z][a-z0-9-]{3,})"
    )

    def test_sls_tool_hints_point_at_projects_with_sls_config(self):
        chains = _load_chains()
        projects = json.loads(
            _RUNTIME_PROJECTS.read_text(encoding="utf-8"))["projects"]
        dead_ends = []
        for chain_name, chain in chains.items():
            for step in chain["steps"]:
                for tool in step.get("tools", []):
                    for match in self._SLS_PROJECT_HINT.finditer(tool):
                        name = match.group(1)
                        if name not in projects:
                            continue
                        if not _has_enabled_sls(projects[name]):
                            dead_ends.append(
                                f"{chain_name}/step{step['id']} ({step['name']}) "
                                f"-> {name}: {tool}"
                            )
        self.assertEqual(
            [], dead_ends,
            "以下链路工具提示指向没有 enabled SLS 配置的项目，agent 执行必然失败；"
            "改用直查模式(--endpoint/--sls-project/--logstore)或换其他取证通道："
            + "; ".join(dead_ends),
        )


if __name__ == "__main__":
    unittest.main()
