"""排查链路引擎 — 定义、编排和约束排查流程

链路定义文件: chains/default.json
会话状态文件: ~/.seek/sessions/{session_id}.json

核心概念:
- chain:  一条排查链路（如"通用排查"、"告警富化排查"）
- step:   链路中的一个步骤（如"查询部署信息"、"查询日志"）
- session: 一次具体的排查会话，跟踪当前进度和上下文
- constraint: 步骤间的约束（如 requires_step=N，表示必须先完成步骤 N）
"""

import json
import os
import re
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock

_PKG_ROOT = Path(__file__).parent
_BUILTIN_CHAINS = _PKG_ROOT / "resources" / "chains" / "default.json"
_USER_CHAINS = seek_path("chains", "default.json")
_SESSION_DIR = seek_path("sessions")
_BUILTIN_TEMPLATES = _PKG_ROOT / "resources" / "chains" / "templates"
_USER_TEMPLATES = seek_path("chains", "templates")
_DEFAULT_REPORT_TEMPLATE = "generic.md"
_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_TEMPLATE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# 可由 `chain start --problem` 提供的首步自然语言输入；其余无生产步骤的
# requiredInputs 必须由 --context 显式注入，避免 flow_id 等标识被描述文本冒充。
PROBLEM_DESCRIPTION_INPUTS = {
    "problem_description",
    "incident_description",
    "error_description",
    "task_description",
    "task_id_or_description",
}
# 兼容别名：存量调用方（test_doc_consistency 等）仍引用下划线名
_PROBLEM_DESCRIPTION_INPUTS = PROBLEM_DESCRIPTION_INPUTS


def _declared_output_producers(steps: list) -> dict:
    """返回每个声明 output 对应的生产步骤编号列表。"""
    producers = {}
    for index, step in enumerate(steps, start=1):
        for output in step.get("outputs", []):
            producers.setdefault(output, []).append(index)
    return producers


def _validate_outputs(step: dict, outputs: dict, require_all: bool) -> Optional[str]:
    """校验步骤提交的 outputs 是否符合链路声明。"""
    if not isinstance(outputs, dict):
        return "outputs must be a JSON object"
    declared = set(step.get("outputs", []))
    provided = set(outputs)
    unknown = sorted(provided - declared)
    if unknown:
        return f"step '{step['name']}' outputs contain undeclared fields: {unknown}"
    if require_all:
        missing = sorted(declared - provided)
        if missing:
            return f"step '{step['name']}' outputs missing declared fields: {missing}"
    return None


class ChainConfigError(ValueError):
    """Raised when a chain definition or persisted session is invalid."""


class EvidenceValidationError(ValueError):
    """Raised when evidence metadata is missing or invalid."""


class TokenUsageValidationError(ValueError):
    """Raised when reported token usage is invalid."""


EVIDENCE_STATUSES = {"FOUND", "NO_DATA", "NOT_APPLICABLE", "TOOL_ERROR"}
TOKEN_USAGE_FIELDS = {"input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"}
EVIDENCE_SCHEMA = {
    "status": sorted(EVIDENCE_STATUSES),
    "sources": [{"tool": "non-empty string", "reference": "non-empty string"}],
    "boundary": "non-empty string",
    "reason": "required when status is not FOUND",
}
TOKEN_USAGE_SCHEMA = {field: "optional non-negative integer"
                      for field in sorted(TOKEN_USAGE_FIELDS)}


def _validate_evidence(step: dict, evidence, enforce_required: bool = True) -> Optional[dict]:
    """Validate and normalize evidence metadata for one step."""
    required = enforce_required and bool(step.get("evidenceRequired", False))
    if evidence is None:
        if required:
            raise EvidenceValidationError(
                f"step '{step['name']}' requires --evidence with status/sources/boundary")
        return None
    if not isinstance(evidence, dict):
        raise EvidenceValidationError("evidence must be a JSON object")
    status = evidence.get("status")
    if status not in EVIDENCE_STATUSES:
        raise EvidenceValidationError(
            f"evidence.status must be one of {sorted(EVIDENCE_STATUSES)}")
    boundary = evidence.get("boundary")
    if not isinstance(boundary, str) or not boundary.strip():
        raise EvidenceValidationError("evidence.boundary must be a non-empty string")
    sources = evidence.get("sources", [])
    if not isinstance(sources, list):
        raise EvidenceValidationError("evidence.sources must be an array")
    if status in {"FOUND", "NO_DATA"} and not sources:
        raise EvidenceValidationError(f"evidence.sources is required when status={status}")
    normalized_sources = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise EvidenceValidationError(f"evidence.sources[{index}] must be an object")
        if not isinstance(source.get("tool"), str) or not source["tool"].strip():
            raise EvidenceValidationError(f"evidence.sources[{index}].tool must be non-empty")
        if not isinstance(source.get("reference"), str) or not source["reference"].strip():
            raise EvidenceValidationError(f"evidence.sources[{index}].reference must be non-empty")
        normalized_sources.append(dict(source))
    reason = evidence.get("reason")
    if status != "FOUND" and (not isinstance(reason, str) or not reason.strip()):
        raise EvidenceValidationError(f"evidence.reason is required when status={status}")
    normalized = dict(evidence)
    normalized["status"] = status
    normalized["boundary"] = boundary.strip()
    normalized["sources"] = normalized_sources
    return normalized


def _validate_token_usage(token_usage) -> Optional[dict]:
    """Validate caller-reported token counts without using them for scoring."""
    if token_usage is None:
        return None
    if not isinstance(token_usage, dict):
        raise TokenUsageValidationError("token_usage must be a JSON object")
    if not token_usage:
        raise TokenUsageValidationError("token_usage must contain at least one token field")
    unknown = sorted(set(token_usage) - TOKEN_USAGE_FIELDS)
    if unknown:
        raise TokenUsageValidationError(f"token_usage contains unknown fields: {unknown}")
    normalized = {}
    for key, value in token_usage.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TokenUsageValidationError(f"token_usage.{key} must be a non-negative integer")
        normalized[key] = value
    return normalized


def _read_chain_file(path: Path, source: str) -> dict:
    """Read and validate one chain definition file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ChainConfigError(f"{source} chain file '{path}' is unreadable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("chains"), dict):
        raise ChainConfigError(f"{source} chain file '{path}' must contain a 'chains' object")
    for name, chain in data["chains"].items():
        _validate_chain(name, chain, source)
    return data


def _validate_chain(name: str, chain: dict, source: str) -> None:
    """Validate the minimum contract required by the chain engine."""
    prefix = f"{source} chain '{name}'"
    if not isinstance(name, str) or not name:
        raise ChainConfigError(f"{prefix} has an invalid name")
    if not isinstance(chain, dict) or not isinstance(chain.get("steps"), list) or not chain["steps"]:
        raise ChainConfigError(f"{prefix} must contain a non-empty steps list")
    step_names = set()
    outputs = set()
    for number, step in enumerate(chain["steps"], start=1):
        if not isinstance(step, dict):
            raise ChainConfigError(f"{prefix}.steps[{number}] must be an object")
        step_name = step.get("name")
        if not isinstance(step_name, str) or not step_name or step_name in step_names:
            raise ChainConfigError(f"{prefix}.steps[{number}].name must be unique and non-empty")
        step_names.add(step_name)
        for field in ("outputs", "requiredInputs"):
            value = step.get(field, [])
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise ChainConfigError(f"{prefix}.steps[{number}].{field} must be a string list")
        evidence_required = step.get("evidenceRequired", False)
        if not isinstance(evidence_required, bool):
            raise ChainConfigError(f"{prefix}.steps[{number}].evidenceRequired must be boolean")
        constraints = step.get("constraints", {})
        if not isinstance(constraints, dict):
            raise ChainConfigError(f"{prefix}.steps[{number}].constraints must be an object")
        requires = constraints.get("requires_step")
        if isinstance(requires, int) and (requires < 1 or requires >= number):
            raise ChainConfigError(f"{prefix}.steps[{number}].constraints.requires_step must reference a prior step")
        outputs.update(step.get("outputs", []))
        condition = step.get("when")
        if condition is not None:
            if not isinstance(condition, dict):
                raise ChainConfigError(f"{prefix}.steps[{number}].when must be an object")
            path = condition.get("path")
            if (not isinstance(path, str) or not path.strip() or path != path.strip()
                    or any(not part for part in path.split("."))):
                raise ChainConfigError(f"{prefix}.steps[{number}].when must contain a non-empty path")
            unknown_keys = sorted(set(condition) - {"path", "equals", "in", "exists"})
            if unknown_keys:
                raise ChainConfigError(
                    f"{prefix}.steps[{number}].when contains unsupported fields: {unknown_keys}")
            operators = [key for key in ("equals", "in", "exists") if key in condition]
            if len(operators) != 1:
                raise ChainConfigError(f"{prefix}.steps[{number}].when must contain exactly one operator")
            if "in" in condition and not isinstance(condition["in"], list):
                raise ChainConfigError(f"{prefix}.steps[{number}].when.in must be an array")
            if "exists" in condition and not isinstance(condition["exists"], bool):
                raise ChainConfigError(f"{prefix}.steps[{number}].when.exists must be boolean")
            skip_outputs = step.get("skipOutputs")
            if not isinstance(skip_outputs, dict) or set(skip_outputs) != set(step.get("outputs", [])):
                raise ChainConfigError(f"{prefix}.steps[{number}].skipOutputs must exactly cover outputs")
    report_template = chain.get("reportTemplate")
    if report_template is not None and (
            not isinstance(report_template, str)
            or not report_template.strip()
            or not _TEMPLATE_NAME_PATTERN.fullmatch(report_template.strip())):
        raise ChainConfigError(f"{prefix}.reportTemplate must be a safe single filename when present")


def _load_chains() -> dict:
    """Load validated built-in chains with validated user overrides."""
    chains = {}
    if _BUILTIN_CHAINS.exists():
        chains.update(_read_chain_file(_BUILTIN_CHAINS, "builtin")["chains"])
    if _USER_CHAINS.exists():
        chains.update(_read_chain_file(_USER_CHAINS, "user")["chains"])
    return chains


def first_step_external_inputs(chain_name: str) -> list:
    """返回链路首步的外部输入键（requiredInputs 中无声明生产步骤的键）。

    这些键只能在会话启动阶段由 --context/--problem 提供，供 start 前置
    校验与 chain list 能力发现使用。
    """
    chain = get_chain(chain_name)
    if chain is None:
        raise ValueError(f"chain '{chain_name}' not found")
    steps = chain.get("steps", [])
    producers = _declared_output_producers(steps)
    return [key for key in steps[0].get("requiredInputs", [])
            if not producers.get(key)]


def missing_start_inputs(chain_name: str, initial_context: dict,
                       problem_description: str) -> list:
    """计算 chain start 时首步仍缺失的外部输入键。

    描述型输入（_PROBLEM_DESCRIPTION_INPUTS）在非空 --problem 下视为满足。
    """
    context = initial_context or {}
    has_problem = bool((problem_description or "").strip())
    missing = []
    for key in first_step_external_inputs(chain_name):
        if key in context:
            continue
        if has_problem and key in PROBLEM_DESCRIPTION_INPUTS:
            continue
        missing.append(key)
    return missing


def list_chains() -> list:
    """列出所有可用的排查链路"""
    chains = _load_chains()
    result = []
    for name, chain in chains.items():
        template = chain.get("reportTemplate")
        steps = chain.get("steps", [])
        producers = _declared_output_producers(steps)
        first_inputs = [key for key in steps[0].get("requiredInputs", [])
                        if not producers.get(key)] if steps else []
        result.append({
            "name": name,
            "title": chain.get("title", name),
            "description": chain.get("description", ""),
            "stepCount": len(steps),
            "steps": [s["name"] for s in steps],
            "firstStepInputs": first_inputs,
            "reportTemplate": template.strip() if isinstance(template, str) and template.strip() else _DEFAULT_REPORT_TEMPLATE,
        })
    return result


def get_chain(name: str) -> Optional[dict]:
    """获取链路定义详情"""
    chains = _load_chains()
    return chains.get(name)


def declared_report_template(chain_name: str) -> str:
    """返回链路声明的报告模板文件名（未声明时回退默认通用模板）。

    仅读链路定义，不做文件解析，供 list 等轻量场景使用。
    """
    chain = get_chain(chain_name)
    if chain is None:
        raise ValueError(f"chain '{chain_name}' not found")
    template = chain.get("reportTemplate")
    return template.strip() if isinstance(template, str) and template.strip() else _DEFAULT_REPORT_TEMPLATE


def get_report_template(chain_name: str) -> dict:
    """解析链路的报告模板文件，返回 {"name", "path"}。

    解析顺序：用户覆盖目录（~/.seek/chains/templates/）→ 内置模板目录；
    同名文件用户版本优先。显式声明的模板缺失时抛 ChainConfigError
    （含搜索路径），不静默回退。
    """
    name = declared_report_template(chain_name)
    if not _TEMPLATE_NAME_PATTERN.fullmatch(name):
        raise ChainConfigError(f"report template '{name}' must be a single safe filename")
    for base in (_USER_TEMPLATES, _BUILTIN_TEMPLATES):
        base = base.resolve()
        candidate = (base / name).resolve()
        if base in candidate.parents and candidate.is_file():
            return {"name": name, "path": str(candidate)}
    raise ChainConfigError(
        f"report template '{name}' for chain '{chain_name}' not found; "
        f"searched: {_USER_TEMPLATES}, {_BUILTIN_TEMPLATES}"
    )


# 报告文件名语义段（slug）：小写 kebab-case，CLI 自动拼接前缀/日期/后缀
_REPORT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_REPORT_SLUG_DATE_PREFIX = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")
_REPORT_SLUG_MAX_LEN = 80


def validate_report_slug(slug: str) -> Optional[str]:
    """校验报告文件名的语义段（场景-业务ID片段-现象）。

    CLI 会自动拼接 ``seek-report-<产出日期>-`` 前缀与 ``.md`` 后缀，
    slug 不得自带这些成分，防止双重前缀。

    Returns:
        非法时返回错误说明；合法返回 None。
    """
    value = (slug or "").strip()
    if not value:
        return "slug must be a non-empty kebab-case string like 'batch-560d6f3c-objectlist-empty'"
    if len(value) > _REPORT_SLUG_MAX_LEN:
        return f"slug too long ({len(value)} chars, max {_REPORT_SLUG_MAX_LEN})"
    if value.startswith("seek-report"):
        return ("slug must not contain the 'seek-report' prefix; "
                "CLI prepends 'seek-report-<date>-' automatically")
    if _REPORT_SLUG_DATE_PREFIX.match(value):
        return "slug must not start with a YYYY-MM-DD date; CLI prepends the report production date"
    if value.endswith(".md"):
        return "slug must not contain the '.md' extension; CLI appends it automatically"
    if not _REPORT_SLUG_PATTERN.match(value):
        return (f"slug '{value}' must be lowercase kebab-case segments [a-z0-9] joined by '-' "
                "(e.g. 'batch-560d6f3c-objectlist-empty')")
    return None


def _render_template_header(template_path: str, session: dict) -> str:
    """读取模板头部块（首个 '---' 分隔线之前）并填充会话可确定的占位符。

    语义占位符（如 ``{主题一句话}``、``{flowId}``）保留给报告产出方填写。
    """
    path = Path(template_path)
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ChainConfigError(f"report template '{path}' is unreadable: {exc}") from exc
    header_lines = []
    for line in content.splitlines():
        if line.strip() == "---":
            break
        header_lines.append(line)
    header = "\n".join(header_lines).rstrip()
    replacements = {
        "{session_id}": str(session.get("session_id") or ""),
        "{chain_name}": str(session.get("chain_name") or ""),
        "{start_time}": str(session.get("started_at") or ""),
        "{end_time}": str(session.get("completed_at") or ""),
        "{problem_description}": str(session.get("problem_description") or ""),
    }
    for placeholder, value in replacements.items():
        header = header.replace(placeholder, value)
    return header


def build_report(session_id: str, slug: str) -> dict:
    """构造报告落盘要素：文件名、模板头部与模板解析结果（不写文件）。

    文件名遵循产出日期前缀规范：``seek-report-YYYY-MM-DD-{slug}.md``，
    日期取命令执行日；slug 为语义段（场景-业务ID片段-现象），
    由调用方归纳，格式由 validate_report_slug 校验。

    Args:
        session_id: 会话 ID（必须已 completed）
        slug: 文件名语义段

    Returns:
        {session_id, chain_name, report_date, slug, filename, template, header_markdown}

    Raises:
        ValueError: 会话不存在、未完成或 slug 非法。
        ChainConfigError: 报告模板缺失或不可读。
    """
    session = get_session(session_id)
    if not session:
        raise ValueError(f"session '{session_id}' not found")
    if session.get("status") != "completed":
        raise ValueError(
            f"session '{session_id}' is not completed (status: {session.get('status')}); "
            "finish all steps before generating the report"
        )
    normalized_slug = (slug or "").strip()
    slug_error = validate_report_slug(normalized_slug)
    if slug_error:
        raise ValueError(slug_error)
    template = get_report_template(session["chain_name"])
    report_date = date.today().isoformat()
    return {
        "session_id": session_id,
        "chain_name": session["chain_name"],
        "report_date": report_date,
        "slug": normalized_slug,
        "filename": f"seek-report-{report_date}-{normalized_slug}.md",
        "template": template,
        "header_markdown": _render_template_header(template["path"], session),
    }


def _context_value(context: dict, path: str):
    """Resolve a dotted path from session context without evaluating expressions."""
    value = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _condition_matches(context: dict, condition: dict) -> bool:
    """Evaluate one validated declarative condition."""
    exists, value = _context_value(context, condition["path"])
    if "exists" in condition:
        return exists == condition["exists"]
    if not exists:
        return False
    if "equals" in condition:
        return value == condition["equals"]
    return value in condition["in"]


def _advance_over_skipped(session: dict, steps: list) -> list:
    """Skip consecutive non-matching conditional steps and return new audit entries."""
    skipped_now = []
    if session.get("routing_contract_version", 0) < 1:
        return skipped_now
    while session["current_step"] <= len(steps):
        number = session["current_step"]
        step = steps[number - 1]
        condition = step.get("when")
        if condition is None or _condition_matches(session.get("context", {}), condition):
            break
        value_exists, value = _context_value(
            session.get("context", {}), condition["path"])
        outputs = deepcopy(step.get("skipOutputs", {}))
        entry = {
            "step": number, "name": step["name"], "title": step.get("title", ""),
            "reason": f"when condition did not match: {condition['path']}",
            "condition": deepcopy(condition),
            "condition_result": False,
            "observed": {"exists": value_exists, "value": deepcopy(value)},
            "outputs": outputs, "skipped_at": datetime.now().isoformat(),
        }
        session.setdefault("skipped_steps", []).append(entry)
        session.setdefault("step_outputs", {})[step["name"]] = outputs
        session.setdefault("context", {})[step["name"]] = deepcopy(outputs)
        skipped_now.append(entry)
        session["current_step"] += 1
    if session["current_step"] > len(steps):
        session["status"] = "completed"
        session["current_step"] = len(steps)
        session["completed_at"] = datetime.now().isoformat()
    return skipped_now


def start_session(chain_name: str, project: str = "",
                  problem_description: str = "",
                  initial_context: dict = None) -> dict:
    """开始一次排查会话

    Args:
        chain_name: 链路名称（如 "default"）
        project: 目标项目名（可选，可在 step 1 中确定）
        problem_description: 问题描述
        initial_context: 初始上下文（可选）— 用户调用时已知的输入（如 flow_id），
            平铺存入 context 顶层，供 step 1 的 requiredInputs 校验命中

    Returns:
        新建的 session dict
    """
    chains = _load_chains()
    if chain_name not in chains:
        raise ValueError(f"chain '{chain_name}' not found; available: {list(chains.keys())}")

    chain = chains[chain_name]
    session_id = uuid.uuid4().hex[:12]
    session = {
        "session_id": session_id,
        "chain_name": chain_name,
        "chain_title": chain.get("title", chain_name),
        "project": project,
        "problem_description": problem_description,
        "started_at": datetime.now().isoformat(),
        "current_step": 1,
        "total_steps": len(chain.get("steps", [])),
        "completed_steps": [],
        "step_outputs": {},
        "step_evidence": {},
        "evidence_contract_version": 1,
        "routing_contract_version": 1,
        "skipped_steps": [],
        "context": dict(initial_context) if initial_context else {},
        "status": "in_progress",
    }
    _advance_over_skipped(session, chain.get("steps", []))
    _save_session(session)
    return session


def get_session(session_id: str) -> Optional[dict]:
    """获取会话状态，损坏文件返回可诊断的配置错误。"""
    _validate_session_id(session_id)
    path = _SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            session = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ChainConfigError(f"session '{session_id}' is corrupt at '{path}': {exc}") from exc
    if not isinstance(session, dict):
        raise ChainConfigError(f"session '{session_id}' is corrupt at '{path}': expected an object")
    return session


def get_current_step(session_id: str) -> Optional[dict]:
    """获取会话当前步骤的完整定义"""
    session = get_session(session_id)
    if not session:
        return None
    if session.get("status") == "completed":
        return None
    chain = get_chain(session["chain_name"])
    if not chain:
        return None
    steps = chain.get("steps", [])
    step_num = session["current_step"]
    if step_num < 1 or step_num > len(steps):
        return None
    step = deepcopy(steps[step_num - 1])
    # 附上会话上下文
    step["session_id"] = session_id
    step["completed_count"] = len(session["completed_steps"])
    step["total_steps"] = session["total_steps"]
    step["is_last_step"] = (step_num == session["total_steps"])
    if step.get("evidenceRequired"):
        step["evidenceSchema"] = deepcopy(EVIDENCE_SCHEMA)
    return step


def complete_step(session_id: str, outputs: dict = None, summary: str = "",
                   evidence: dict = None, token_usage: dict = None) -> dict:
    """标记当前步骤完成，推进到下一步

    整个「读-校验-改-写」周期持有会话文件锁，防止并发操作同一会话时
    丢失更新（读在锁外会让后写覆盖先写）。

    Args:
        session_id: 会话 ID
        outputs: 该步骤的输出（存入会话上下文供后续步骤使用）
        summary: 该步骤的执行摘要
        evidence: 结构化证据元数据；evidenceRequired 步骤必填
        token_usage: 调用方上报的 token 使用量，仅统计、不参与流程判断

    Returns:
        更新后的 session（含 next_step 信息）
    """
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            raise ValueError(f"session '{session_id}' not found")
        if session["status"] != "in_progress":
            raise ValueError(f"session is already '{session['status']}'")

        chain = get_chain(session["chain_name"])
        steps = chain.get("steps", [])
        step_num = session["current_step"]
        if step_num > len(steps):
            raise ValueError(f"invalid step number {step_num}")

        step = steps[step_num - 1]
        step_name = step["name"]
        outputs = {} if outputs is None else outputs
        output_error = _validate_outputs(step, outputs, require_all=True)
        if output_error:
            raise ValueError(output_error)
        normalized_evidence = _validate_evidence(
            step, evidence, enforce_required=session.get("evidence_contract_version", 0) >= 1)
        normalized_token_usage = _validate_token_usage(token_usage)

        # 硬约束：complete 前自动重校验当前步骤约束（requires_step/requiredInputs），
        # 防止跳步或前序 outputs 缺失时仍推进链路
        validation = validate_step(session_id, step_num)
        if not validation.get("valid", False):
            raise ValueError(
                f"cannot complete step {step_num} ('{step_name}'): "
                f"{validation.get('reason', 'validation failed')}"
            )

        # 记录完成
        completed = {
            "step": step_num,
            "name": step_name,
            "title": step.get("title", ""),
            "summary": summary,
            "outputs": outputs or {},
            "completed_at": datetime.now().isoformat(),
        }
        if normalized_evidence is not None:
            completed["evidence"] = normalized_evidence
        if normalized_token_usage is not None:
            completed["token_usage"] = normalized_token_usage
        session["completed_steps"].append(completed)
        session["step_outputs"][step_name] = outputs or {}
        if normalized_evidence is not None:
            session.setdefault("step_evidence", {})[step_name] = normalized_evidence

        # 合并 outputs 到 context，使用命名空间前缀避免不同步骤输出同名 key 互相覆盖
        if outputs:
            session["context"][step_name] = dict(outputs)

        # 推进或完成
        if step_num >= session["total_steps"]:
            session["status"] = "completed"
            session["completed_at"] = datetime.now().isoformat()
            session["current_step"] = step_num  # 保持
        else:
            session["current_step"] = step_num + 1
            _advance_over_skipped(session, steps)

        _write_session_file(session)
    return session


def validate_step(session_id: str, target_step: int) -> dict:
    """验证是否可以执行目标步骤（检查约束）

    Args:
        session_id: 会话 ID
        target_step: 目标步骤编号

    Returns:
        {"valid": bool, "reason": str, "missing_prerequisites": [...]}
    """
    session = get_session(session_id)
    if not session:
        return {"valid": False, "reason": f"session '{session_id}' not found"}

    chain = get_chain(session["chain_name"])
    steps = chain.get("steps", [])
    if target_step < 1 or target_step > len(steps):
        return {"valid": False, "reason": f"step {target_step} out of range (1-{len(steps)})"}

    step = steps[target_step - 1]
    skipped_entry = next(
        (entry for entry in session.get("skipped_steps", [])
         if entry.get("step") == target_step), None)
    if skipped_entry is not None:
        return {
            "valid": False,
            "reason": f"step {target_step} ('{step['name']}') was skipped by its when condition",
            "missing_prerequisites": [],
            "state": "skipped",
            "skip": skipped_entry,
        }
    constraints = step.get("constraints", {})
    if constraints.get("must_be_first", False) and target_step != 1:
        return {
            "valid": False,
            "reason": f"step {target_step} ('{step['name']}') is marked must_be_first but is not step 1",
            "missing_prerequisites": [],
        }
    completed_nums = {s["step"] for s in session["completed_steps"]}
    resolved_nums = completed_nums | {s["step"] for s in session.get("skipped_steps", [])}

    # 检查 requires_step 约束
    # 约定：requires_step 表示前置步骤的 step 编号（与 completed_steps["step"] 一致）。
    # 若定义中使用自定义 id 字段，则通过映射解析为编号后再比较。
    requires = constraints.get("requires_step")
    if requires is not None:
        # 优先按编号匹配；否则按 id 字段查找并解析为编号
        resolved_num = requires if isinstance(requires, int) and requires in resolved_nums else None
        if resolved_num is None:
            for i, s in enumerate(steps, start=1):
                if s.get("id") == requires:
                    resolved_num = i
                    break
        if resolved_num is None or resolved_num not in resolved_nums:
            missing_step = next(
                (s for s in steps if s.get("id") == requires), None
            )
            missing_name = missing_step["name"] if missing_step else f"step {requires}"
            return {
                "valid": False,
                "reason": f"step {target_step} ('{step['name']}') requires step {requires} ('{missing_name}') to be completed first",
                "missing_prerequisites": [requires],
            }

    # 检查 requires_all_previous 约束（必须按顺序完成所有前置步骤）
    if constraints.get("requires_all_previous", False):
        missing = [i for i in range(1, target_step) if i not in resolved_nums]
        if missing:
            return {
                "valid": False,
                "reason": f"step {target_step} requires all previous steps to be completed; missing: {missing}",
                "missing_prerequisites": missing,
            }

    # 检查 required_inputs 是否已满足。链路声明过的 output 只能由对应的
    # 已完成生产步骤提供；无生产者的字段则是外部输入。
    required_inputs = step.get("requiredInputs", [])
    context = session.get("context", {})
    producers = _declared_output_producers(steps)
    missing_inputs = []
    for required_input in required_inputs:
        producer_steps = producers.get(required_input, [])
        if producer_steps:
            available = any(
                required_input in session.get("step_outputs", {}).get(steps[producer_step - 1]["name"], {})
                for producer_step in producer_steps
                if producer_step in resolved_nums
            )
        else:
            available = required_input in context
            if (not available and target_step == 1
                    and required_input in PROBLEM_DESCRIPTION_INPUTS):
                available = bool(session.get("problem_description", "").strip())
        if not available:
            missing_inputs.append(required_input)
    if missing_inputs:
        return {
            "valid": False,
            "reason": f"step {target_step} requires inputs not yet available from declared sources: {missing_inputs}",
            "missing_prerequisites": [],
            "missing_inputs": missing_inputs,
        }

    return {
        "valid": True,
        "reason": f"step {target_step} ('{step['name']}') is ready to execute",
        "step": step,
    }


def amend_step(session_id: str, target_step: int, outputs: dict = None,
               summary: str = "", evidence: dict = None) -> dict:
    """回填更正已完成的步骤（不覆盖原始 outputs，保留排查过程真实性）

    场景：排查后期发现前序步骤结论有误（如误判"日志未接入"），
    用本命令追加更正记录，并把更正后的 outputs 合并进会话上下文。
    completed 状态的会话也允许回填。

    Args:
        session_id: 会话 ID
        target_step: 要更正的步骤编号（必须已完成）
        outputs: 更正后的输出（merge 进该步骤命名空间）
        summary: 更正说明（何时、因何、更正了什么）
        evidence: 更正后的结构化证据元数据

    Returns:
        更新后的 session
    """
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            raise ValueError(f"session '{session_id}' not found")

        chain = get_chain(session["chain_name"])
        steps = chain.get("steps", [])
        if target_step < 1 or target_step > len(steps):
            raise ValueError(f"step {target_step} out of range (1-{len(steps)})")

        completed_entry = next(
            (s for s in session["completed_steps"] if s["step"] == target_step), None
        )
        if completed_entry is None:
            raise ValueError(
                f"step {target_step} 尚未完成，不能 amend；请先按正常流程 complete"
            )

        step_name = steps[target_step - 1]["name"]
        outputs = {} if outputs is None else outputs
        output_error = _validate_outputs(steps[target_step - 1], outputs, require_all=False)
        if output_error:
            raise ValueError(output_error)
        normalized_evidence = _validate_evidence(
            steps[target_step - 1], evidence,
            enforce_required=session.get("evidence_contract_version", 0) >= 1,
        ) if (outputs or evidence is not None) else None

        # 追加更正记录（原始 completed_steps 条目不覆盖）
        session.setdefault("amendments", []).append({
            "step": target_step,
            "name": step_name,
            "summary": summary,
            "outputs": outputs,
            "evidence": normalized_evidence,
            "amended_at": datetime.now().isoformat(),
        })
        completed_entry["amended"] = True

        # 把更正后的 outputs merge 进上下文，供后续/报告使用
        if outputs:
            session["step_outputs"].setdefault(step_name, {}).update(outputs)
            session["context"].setdefault(step_name, {}).update(outputs)
            if isinstance(session["context"].get(step_name), dict):
                session["context"][step_name]["_has_correction"] = True
        if normalized_evidence is not None:
            session.setdefault("step_evidence", {})[step_name] = normalized_evidence

        _write_session_file(session)
    return session


def provide_inputs(session_id: str, inputs: dict) -> dict:
    """向未完成会话补注入外部输入（平铺 merge 进 context 顶层）

    与 start --context 语义一致：供首步无生产者的 requiredInputs 校验命中。
    键名与任一步骤名冲突时拒绝（防 complete 时命名空间静默覆盖）。

    Args:
        session_id: 会话 ID
        inputs: 要注入的键值对（JSON 对象）

    Returns:
        更新后的 session
    """
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            raise ValueError(f"session '{session_id}' not found")
        if session["status"] == "completed":
            raise ValueError(f"session '{session_id}' is already completed")
        if not isinstance(inputs, dict):
            raise ValueError("inputs must be a JSON object")

        chain = get_chain(session["chain_name"])
        step_names = {s.get("name") for s in chain.get("steps", [])}
        conflict = set(inputs) & step_names
        if conflict:
            raise ValueError(f"input keys conflict with step names: {sorted(conflict)}")

        session.setdefault("context", {}).update(inputs)
        _write_session_file(session)
    return session


def get_context(session_id: str) -> dict:
    """获取会话累积的上下文（所有已完成步骤的输出）"""
    session = get_session(session_id)
    if not session:
        return {}
    # 模板解析失败降级为 error 字段，不阻断 context 输出（报告产出优先）
    try:
        report_template = get_report_template(session["chain_name"])
    except (ChainConfigError, ValueError) as exc:
        report_template = {"name": "", "error": str(exc)}
    return {
        "session_id": session_id,
        "chain_name": session["chain_name"],
        "project": session.get("project", ""),
        "problem_description": session.get("problem_description", ""),
        "context": session.get("context", {}),
        "step_evidence": session.get("step_evidence", {}),
        "token_usage": get_token_usage(session_id),
        "completed_steps": [
            {"step": s["step"], "name": s["name"], "summary": s.get("summary", "")}
            for s in session["completed_steps"]
        ],
        "current_step": session["current_step"],
        "status": session["status"],
        "amendments": session.get("amendments", []),
        "skipped_steps": session.get("skipped_steps", []),
        "report_template": report_template,
    }


def get_token_usage(session_id: str) -> Optional[dict]:
    """汇总会话中调用方上报的 token 使用量；仅用于统计。"""
    session = get_session(session_id)
    if not session:
        return None
    totals = {key: 0 for key in sorted(TOKEN_USAGE_FIELDS)}
    steps = []
    reported = 0
    for entry in session.get("completed_steps", []):
        usage = entry.get("token_usage")
        if usage is None:
            steps.append({"step": entry["step"], "name": entry["name"], "reported": False})
            continue
        reported += 1
        for key, value in usage.items():
            totals[key] += value
        steps.append({"step": entry["step"], "name": entry["name"],
                      "reported": True, "token_usage": usage})
    return {
        "session_id": session_id,
        "totals": {**totals, "total_tokens": totals["input_tokens"] + totals["output_tokens"]},
        "steps": steps,
        "reported_steps": reported,
        "completed_steps": len(session.get("completed_steps", [])),
        "complete": reported == len(session.get("completed_steps", [])),
        "used_for_scoring": False,
    }


def list_sessions(limit: int = 20) -> list:
    """列出最近的排查会话；损坏文件作为独立条目返回。"""
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for path in sorted(_SESSION_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                s = json.load(f)
            if not isinstance(s, dict):
                raise ValueError("expected an object")
            sessions.append({
                "session_id": s["session_id"],
                "chain_name": s["chain_name"],
                "project": s.get("project", ""),
                "status": s["status"],
                "current_step": s["current_step"],
                "total_steps": s["total_steps"],
                "started_at": s["started_at"],
                "problem_description": s.get("problem_description", "")[:100],
            })
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            sessions.append({"session_id": path.stem, "status": "corrupt", "path": str(path),
                             "error": str(exc)[:200]})
        if len(sessions) >= limit:
            break
    return sessions


@contextmanager
def _session_lock(session_id: str):
    """Serialize writes for a session across CLI processes."""
    _validate_session_id(session_id)
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with file_lock(_SESSION_DIR / f"{session_id}.lock"):
        yield


def _save_session(session: dict) -> None:
    """Atomically save session state while preserving a last valid file."""
    with _session_lock(session["session_id"]):
        _write_session_file(session)


def _write_session_file(session: dict) -> None:
    """锁内写入原语：调用方必须已持有该会话的 _session_lock。

    同进程用新 fd 二次 flock 会死锁，锁内路径禁止再调 _save_session。
    """
    session_id = session.get("session_id") if isinstance(session, dict) else None
    _validate_session_id(session_id)
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = _SESSION_DIR / f"{session_id}.json"
    atomic_write_json(path, session, default=str)


def _validate_session_id(session_id: str) -> None:
    """Reject path-like IDs before they reach filesystem APIs."""
    if not isinstance(session_id, str) or not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("invalid session_id; expected a 12-character lowercase hex id")
