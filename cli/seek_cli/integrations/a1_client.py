"""A1 CLI 封装 — 查询部署信息、应用详情、变更记录等

A1 CLI 是阿里云 Aone 平台的命令行工具，支持 JSON 输出。
本模块通过 subprocess 调用 a1 命令，解析 JSON 结果。
"""

import json
import subprocess
import shutil
from typing import Optional

from seek_cli.perf_log import perf_span


A1_CLI_GUIDE_URL = "https://a1.io.alibaba-inc.com/docs/guide/"


def _check_a1() -> str:
    """检查 a1 CLI 是否可用，返回可执行路径"""
    a1_path = shutil.which("a1")
    if not a1_path:
        raise RuntimeError(
            f"a1 CLI not found. Install guide: {A1_CLI_GUIDE_URL}\n"
            "Then run: a1 auth login"
        )
    return a1_path


def _redact_arg(value: str) -> str:
    """Keep command failures useful without logging sensitive arguments."""
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _run_a1(args: list) -> dict:
    """执行 a1 命令并返回解析后的 JSON

    Args:
        args: a1 子命令参数列表（不含 a1 本身）

    Returns:
        解析后的 JSON dict
    """
    _check_a1()
    cmd = ["a1"] + args + ["--format", "json"]
    # perf 观测（L2 集成级）：每次 a1 subprocess 调用一条记录。
    # returncode 检查必须在 span 内：失败路径 raise 才能被记为 status=error。
    with perf_span(f"a1 {' '.join(args[:3])}", "a1_subprocess",
                   {"cmd": " ".join(args)}) as span:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=False)
        span["returncode"] = result.returncode
        if result.returncode != 0:
            safe_cmd = " ".join(_redact_arg(item) for item in cmd)
            raise RuntimeError(
                f"a1 command failed: {safe_cmd}\nstderr: {_redact_arg(result.stderr)}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # 如果不是 JSON，返回原始文本
        return {"raw_output": result.stdout.strip()}


def get_app_info(app_name: str) -> dict:
    """查询 Aone 应用详情

    Args:
        app_name: Aone 应用名

    Returns:
        应用信息 dict（含部署分支、环境等）
    """
    return _run_a1(["app", "view", app_name])


def list_apps(keyword: str = "", status: str = "") -> dict:
    """搜索 Aone 应用列表

    Args:
        keyword: 搜索关键词
        status: 状态过滤（如 ONLINE,READY_TO_ONLINE）

    Returns:
        应用列表
    """
    args = ["app", "list"]
    if keyword:
        args += ["--keyword", keyword]
    if status:
        args += ["--status", status]
    return _run_a1(args)


def list_deploy_orders(app_name: str, pipeline: str = "") -> dict:
    """查询应用的部署单列表

    Args:
        app_name: Aone 应用名
        pipeline: pipeline 名称（可选）

    Returns:
        部署单列表
    """
    args = ["app", "deploy-order", "list", "--app", app_name]
    if pipeline:
        args += ["--pipeline", pipeline]
    return _run_a1(args)


def get_deploy_order(order_id: str) -> dict:
    """查询部署单详情

    Args:
        order_id: 部署单 ID

    Returns:
        部署单详情（含分支、提交、环境等）
    """
    return _run_a1(["app", "deploy-order", "get", order_id])


def list_change_requests(app_name: str) -> dict:
    """查询应用的变更单列表

    Args:
        app_name: Aone 应用名

    Returns:
        变更单列表
    """
    return _run_a1(["app", "cr", "list", "--app", app_name])


def get_repo_info(repo_path: str) -> dict:
    """查询代码仓库详情

    Args:
        repo_path: 仓库路径（group/project 格式）

    Returns:
        仓库信息
    """
    return _run_a1(["repo", "view", "--repo", repo_path])


def list_repo_branches(repo_path: str) -> dict:
    """查询代码仓库分支列表

    Args:
        repo_path: 仓库路径

    Returns:
        分支列表
    """
    return _run_a1(["repo", "branch", "list", "--repo", repo_path])


def _extract_commits(branch_info: dict) -> list:
    """从 pipeline 分支信息的变更单中尽力提取 commit 标识。"""
    commits = []
    for cr in branch_info.get("changeRequests", []) or []:
        if not isinstance(cr, dict):
            continue
        for key in ("commit", "commitId", "commitSHA", "revision"):
            if cr.get(key):
                commits.append(str(cr[key]))
                break
    return commits


def query_deployed_branch(app_name: str) -> dict:
    """查询应用实际部署的分支信息（组合查询）

    这是一个便捷方法，组合 app view + pipeline list + pipeline branch 来获取：
    - 各 pipeline 最近一次实例的发布分支（releaseBranch）
    - 变更单中的 commit（若 A1 返回）
    - 应用元信息

    Args:
        app_name: Aone 应用名

    Returns:
        部署信息摘要: {app_name, app_info, deployments, release_branches, commits}；
        无法解析任何 pipeline 实例时附 warnings（仅应用元信息，不代表线上版本）
    """
    info = get_app_info(app_name)
    # 从 app view 结果中提取部署相关信息
    # A1 返回结构可能包含: deployInfo, branches, environments 等
    deploy_summary = {
        "app_name": app_name,
        "app_info": info,
    }
    # 尝试提取关键字段
    if isinstance(info, dict):
        for key in ["deployInfo", "deployBranch", "currentBranch", "environments", "pipelines"]:
            if key in info:
                deploy_summary[key] = info[key]

    deployments = []
    try:
        pipelines = list_pipelines(app_name)
    except RuntimeError as e:
        pipelines = []
        deploy_summary.setdefault("warnings", []).append(
            f"pipeline 列表获取失败（{e}），仅返回应用元信息"
        )
    for p in pipelines:
        if not isinstance(p, dict):
            continue
        instance_id = p.get("latestPipelineInstanceId")
        if not instance_id:
            continue
        try:
            branch_info = get_pipeline_branch(app_name, instance_id)
        except RuntimeError as e:
            deployments.append({
                "pipelineName": p.get("pipelineName"),
                "instanceId": instance_id,
                "error": str(e)[:200],
            })
            continue
        if isinstance(branch_info, dict):
            branch_info.setdefault("pipelineName", p.get("pipelineName"))
            branch_info.setdefault("pipelineStatus", p.get("status"))
            branch_info.setdefault("instanceId", instance_id)
            deployments.append(branch_info)

    deploy_summary["deployments"] = deployments
    deploy_summary["release_branches"] = sorted({
        d.get("releaseBranch") for d in deployments
        if isinstance(d, dict) and d.get("releaseBranch")
    })
    commits = sorted({c for d in deployments if isinstance(d, dict)
                      for c in _extract_commits(d)})
    deploy_summary["commits"] = commits
    if not deployments:
        deploy_summary.setdefault("warnings", []).append(
            "未解析到任何 pipeline 实例的部署分支，仅返回应用元信息，"
            "不能代表线上版本；可用 seek deploy env <project> --env <env> 按环境核对"
        )
    return deploy_summary


def list_pipelines(app_name: str) -> list:
    """查询应用的 pipeline 列表（每个 pipeline 对应一个环境）

    Args:
        app_name: Aone 应用名

    Returns:
        pipeline 列表，每项含: pipelineId, pipelineName, status, latestPipelineInstanceId
    """
    result = _run_a1(["app", "pipeline", "list", "--app", app_name])
    if isinstance(result, list):
        return result
    return result.get("pipelines", result.get("data", []))


def get_pipeline_branch(app_name: str, instance_id: int) -> dict:
    """查询 pipeline instance 的发布分支和变更列表

    Args:
        app_name: Aone 应用名
        instance_id: pipeline instance ID

    Returns:
        含 releaseBranch, status, changeRequests, instanceUrl 等
    """
    return _run_a1([
        "app", "pipeline", "branch",
        "--app", app_name,
        "--instance-id", str(instance_id),
    ])


# 环境同义词组：用户输入的任一别名都会展开为整组关键词依次匹配 pipeline 名。
# 复盘背景：pipeline 命名不统一（如"正式-云网络ASO"），用 `生产` 直查会 0 命中。
_ENV_SYNONYMS = {
    "日常": ["日常", "daily", "test", "测试"],
    "预发": ["预发", "pre", "staging", "stage"],
    "正式": ["正式", "prod", "生产", "production", "online", "线上"],
}
_ENV_ALIAS_TO_CANONICAL = {
    alias.casefold(): canonical
    for canonical, aliases in _ENV_SYNONYMS.items()
    for alias in aliases
}
_PIPELINE_NAME_FIELDS = ("pipelineName", "name", "displayName", "environmentName")


def _match_pipelines(pipelines: list, env_keyword: str) -> tuple:
    """按环境同义词组和安全字符串字段匹配 A1 pipeline。

    Returns:
        (matched, candidates)：matched 为 [(pipeline, ["字段:命中词", ...]), ...]，
        candidates 为本次实际尝试的关键词列表
    """
    kw = str(env_keyword).strip()
    canonical = _ENV_ALIAS_TO_CANONICAL.get(kw.casefold(), kw)
    candidates = _ENV_SYNONYMS.get(canonical, [canonical])
    matched = []
    for pipeline in pipelines:
        if not isinstance(pipeline, dict):
            continue
        hits = []
        for candidate in candidates:
            for field in _PIPELINE_NAME_FIELDS:
                value = pipeline.get(field)
                if not isinstance(value, str) or candidate not in value:
                    continue
                if candidate == "正式" and "非正式" in value:
                    continue
                hits.append(f"{field}:{candidate}")
        if hits:
            matched.append((pipeline, hits))
    return matched, candidates


def query_env_deploy(app_name: str, env_keyword: str = "日常") -> dict:
    """查询指定环境的部署信息（组合查询）

    自动完成: pipeline 列表 → 环境匹配（同义词自动扩展） → 分支查询

    Args:
        app_name: Aone 应用名
        env_keyword: 环境关键词（如 "日常"、"预发"、"正式"，或别名
            daily/pre/prod/生产/online 等，自动展开为同义词组匹配）

    Returns:
        {
            "app_name": ...,
            "env_keyword": ...,
            "matched_pipelines": [...],
            "deployments": [{pipelineName, releaseBranch, status, changeRequests, ...}]
        }
    """
    pipelines = list_pipelines(app_name)
    matched_with_fields, candidates = _match_pipelines(pipelines, env_keyword)
    matched = [pipeline for pipeline, _ in matched_with_fields]

    deployments = []
    for p in matched:
        instance_id = p.get("latestPipelineInstanceId")
        if not instance_id:
            continue
        branch_info = get_pipeline_branch(app_name, instance_id)
        deployments.append(branch_info)

    if matched:
        hint = ""
    else:
        names = [p.get("pipelineName") for p in pipelines
                 if isinstance(p, dict) and p.get("pipelineName")]
        hint = (
            f"未匹配到环境 '{env_keyword}' 的 pipeline（已尝试关键词: "
            f"{', '.join(candidates)}）。请从实际 pipeline 名中就近选择: "
            f"{'；'.join(names) or '（无 pipeline）'}，或换用 日常/预发/正式 及其别名重试"
        )

    return {
        "app_name": app_name,
        "env_keyword": env_keyword,
        "match_keyword": candidates,
        "match_fields": {
            str(pipeline.get("pipelineId", pipeline.get("pipelineName", ""))): fields
            for pipeline, fields in matched_with_fields
        },
        "all_pipelines": [
            {"pipelineId": p.get("pipelineId"), "name": p.get("pipelineName"),
             "status": p.get("status"), "instanceId": p.get("latestPipelineInstanceId")}
            for p in pipelines if isinstance(p, dict)
        ],
        "matched_count": len(matched),
        "deployments": deployments,
        "hint": hint,
    }
