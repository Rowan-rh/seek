"""Agent Harness 离线就绪检查。"""

import os
import shutil
import tempfile
from pathlib import Path

from seek_cli import __version__, agent_eval, chain, config
from seek_cli.commands import skill
from seek_cli.output import error, success
from seek_cli.plugins import get_provider
from seek_cli.paths import seek_home, seek_home_source


_alibaba = get_provider("alibaba")
expert_client = _alibaba.service("expert")
roar_client = _alibaba.service("roar")


def _check(name: str, status: str, message: str, data=None) -> dict:
    """构造稳定的 Harness 检查项。"""
    item = {"name": name, "status": status, "message": message}
    if data is not None:
        item["data"] = data
    return item


def _check_storage() -> dict:
    """实际创建并删除临时文件，验证 seek home 可写。"""
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
    """检查内置项目、链路及报告模板，不访问外部服务。"""
    checks = []
    try:
        projects = config.list_projects()
        checks.append(_check("project-resources", "pass", "项目配置可读取", {
            "project_count": len(projects),
        }))
    except (config.ProjectConfigError, OSError, ValueError) as exc:
        checks.append(_check("project-resources", "failure", str(exc)))

    try:
        chains = chain.list_chains()
        template_names = set()
        for item in chains:
            template_names.add(chain.get_report_template(item["name"])["name"])
        checks.append(_check("chain-resources", "pass", "链路和报告模板可读取", {
            "chain_count": len(chains),
            "templates": sorted(template_names),
        }))
    except (chain.ChainConfigError, OSError, ValueError) as exc:
        checks.append(_check("chain-resources", "failure", str(exc)))
    return checks


def _check_versions() -> dict:
    """检查源码 Skill 声明与运行时 CLI 版本是否一致。"""
    source_info = skill.get_source_info()
    consistency = skill.version_consistency(source_info)
    state = consistency["consistent"]
    if state is False:
        return _check("skill-cli-version", "failure", "Skill 与 CLI 版本声明不一致", consistency)
    if state is None:
        return _check("skill-cli-version", "warning", "当前安装形态无法读取 Skill 版本声明", {
            **consistency, "actual_cli_version": __version__,
        })
    return _check("skill-cli-version", "pass", "Skill 与 CLI 版本一致", consistency)


def _check_external_commands() -> list:
    """检查可选外部命令是否在 PATH；缺失只告警。"""
    checks = []
    for command in ("a1", "dws"):
        path = shutil.which(command)
        if path:
            checks.append(_check(f"command-{command}", "pass", f"{command} 可用", {"path": path}))
        else:
            checks.append(_check(f"command-{command}", "warning", f"{command} 不在 PATH"))
    return checks


def _check_hosts() -> list:
    """报告外部 HTTP host 的传输风险，不发起请求。"""
    checks = []
    for name, host in (("expert", expert_client.get_host()), ("roar", roar_client.get_host())):
        status = "warning" if host.lower().startswith("http://") else "pass"
        message = f"{name} 使用明文 HTTP" if status == "warning" else f"{name} 使用 HTTPS"
        checks.append(_check(f"host-{name}", status, message, {"host": host}))
    return checks


def build_readiness_report() -> dict:
    """执行全部离线检查并返回汇总报告。"""
    checks = [_check_storage()]
    checks.extend(_check_resources())
    checks.append(_check_versions())
    checks.extend(_check_external_commands())
    checks.extend(_check_hosts())
    counts = {state: sum(item["status"] == state for item in checks)
              for state in ("pass", "warning", "failure")}
    return {
        "ready": counts["failure"] == 0,
        "seek_home": str(seek_home()),
        "seek_home_source": seek_home_source(),
        "summary": counts,
        "checks": checks,
        "network_accessed": False,
    }


def cmd_harness_check(args) -> dict:
    """运行离线 Harness 就绪检查。"""
    report = build_readiness_report()
    if not report["ready"]:
        return error("Harness 就绪检查失败", code="HARNESS_NOT_READY", data=report)
    return success(report, message="Harness 就绪检查通过")


def cmd_harness_evaluate(args) -> dict:
    """运行 Agent 场景 replay 或外部 runner 实时评测。"""
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
