"""Agent Harness 离线就绪检查。"""

import os
import tempfile
from pathlib import Path

from seek_cli import __version__, agent_eval, chain, config
from seek_cli.commands import skill
from seek_cli.output import error, success
from seek_cli.paths import seek_home, seek_home_source


def _check(name: str, status: str, message: str, data=None) -> dict:
    item = {"name": name, "status": status, "message": message}
    if data is not None:
        item["data"] = data
    return item


def _check_storage() -> dict:
    home = seek_home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".harness-probe-", dir=str(home))
        os.close(fd)
        Path(probe).unlink()
    except OSError as exc:
        return _check("storage", "failure", f"seek home 不可写: {exc}", {
            "path": str(home), "source": seek_home_source(),
        })
    return _check("storage", "pass", "seek home 可写", {
        "path": str(home), "source": seek_home_source(),
    })


def _check_resources() -> list:
    checks = []
    try:
        checks.append(_check("project-resources", "pass", "项目配置可读取", {
            "project_count": len(config.list_projects()),
        }))
    except (config.ProjectConfigError, OSError, ValueError) as exc:
        checks.append(_check("project-resources", "failure", str(exc)))
    try:
        chains = chain.list_chains()
        templates = sorted({chain.get_report_template(item["name"])["name"] for item in chains})
        checks.append(_check("chain-resources", "pass", "链路和报告模板可读取", {
            "chain_count": len(chains), "templates": templates,
        }))
    except (chain.ChainConfigError, OSError, ValueError) as exc:
        checks.append(_check("chain-resources", "failure", str(exc)))
    return checks


def _check_versions() -> dict:
    source_info = skill.get_source_info()
    consistency = skill.version_consistency(source_info)
    if consistency["consistent"] is False:
        return _check("skill-cli-version", "failure", "Skill 与 CLI 版本声明不一致", consistency)
    if consistency["consistent"] is None:
        return _check("skill-cli-version", "warning", "无法读取 Skill 版本声明", consistency)
    return _check("skill-cli-version", "pass", "Skill 与 CLI 版本一致", consistency)


def build_readiness_report() -> dict:
    checks = [_check_storage(), *_check_resources(), _check_versions()]
    counts = {state: sum(item["status"] == state for item in checks)
              for state in ("pass", "warning", "failure")}
    return {
        "ready": counts["failure"] == 0,
        "seek_home": str(seek_home()),
        "seek_home_source": seek_home_source(),
        "version": __version__,
        "summary": counts,
        "checks": checks,
        "network_accessed": False,
    }


def cmd_harness_check(args) -> dict:
    report = build_readiness_report()
    if not report["ready"]:
        return error("Harness 就绪检查失败", code="HARNESS_NOT_READY", data=report)
    return success(report, message="Harness 就绪检查通过")


def cmd_harness_evaluate(args) -> dict:
    try:
        scenario_set = agent_eval.load_scenario_set(args.scenarios)
        report = agent_eval.run_scenarios(
            scenario_set,
            agent_command=getattr(args, "agent_command", None),
            timeout=getattr(args, "timeout", 120),
            scenario_ids=getattr(args, "scenario_ids", None),
        )
    except agent_eval.AgentEvalConfigError as exc:
        return error(str(exc), code="AGENT_EVAL_CONFIG_ERROR")
    if report["status"] != "ok":
        return error("Agent 场景评测失败", code="AGENT_EVAL_FAILED", data=report)
    return success(report, message="Agent 场景评测通过")
