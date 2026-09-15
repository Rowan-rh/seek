"""排查链路管理命令 — 编排和约束排查流程"""

import json

from seek_cli import chain as chain_engine
from seek_cli.output import success, error


def _parse_json_object(raw, option_name: str):
    """解析可选 JSON 对象参数，返回 (value, error_response)。"""
    if not raw:
        return None, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None, error(f"invalid JSON for {option_name}: {raw}", code="BAD_JSON")
    if not isinstance(value, dict):
        return None, error(f"{option_name} must be a JSON object", code="BAD_JSON")
    return value, None


def _guarded_session_call(fn, *args):
    """执行会话相关引擎调用，把会话 id 异常统一映射为错误响应。

    返回 (value, error_result)，二者恰有一个非 None。value 为业务未命中
    （None/{}/valid=False）时不算错误，由调用方按 NOT_FOUND 等既有语义处理。
    - ChainConfigError 是 ValueError 子类，必须先捕获：损坏会话要保留路径级诊断，
      否则会被下面的 ValueError 分支吞掉而误报为“不存在”。
    - ValueError：非法 session_id 属用户输入错误 → BAD_ARGUMENT，
      不再冒泡到全局兜底误报 INTERNAL_ERROR。
    """
    try:
        return fn(*args), None
    except chain_engine.ChainConfigError as e:
        return None, error(str(e), code="CHAIN_CONFIG_ERROR")
    except ValueError as e:
        return None, error(str(e), code="BAD_ARGUMENT")


def cmd_chain_list(args) -> dict:
    """列出所有可用的排查链路"""
    chains = chain_engine.list_chains()
    return success({"chains": chains, "total": len(chains)},
                    message=f"共 {len(chains)} 条链路")


def cmd_chain_show(args) -> dict:
    """查看链路详情（含所有步骤）"""
    c = chain_engine.get_chain(args.name)
    if not c:
        return error(f"chain '{args.name}' not found", code="NOT_FOUND")
    return success(c, message=f"链路: {c.get('title', args.name)}")


def cmd_chain_start(args) -> dict:
    """开始一次排查会话"""
    # 链路存在性前置检查，避免缺键报错时误入建会话流程
    chain = chain_engine.get_chain(args.name)
    if not chain:
        chains = chain_engine.list_chains()
        return error(
            f"chain '{args.name}' not found; available: {[c['name'] for c in chains]}",
            code="CHAIN_NOT_FOUND")

    # 解析初始上下文 (JSON 字符串)，如 '{"flow_id": "FLOW-xxx"}'
    initial_context = {}
    if getattr(args, "context", None):
        try:
            initial_context = json.loads(args.context)
        except json.JSONDecodeError:
            return error(f"invalid JSON for --context: {args.context}", code="BAD_JSON")
        if not isinstance(initial_context, dict):
            return error("--context must be a JSON object", code="BAD_JSON")
        # 防止注入的 key 与步骤名同名：complete 时 context[step_name] 会静默覆盖
        step_names = {s.get("name") for s in chain.get("steps", [])}
        conflict = set(initial_context) & step_names
        if conflict:
            return error(f"--context keys conflict with step names: {sorted(conflict)}",
                         code="BAD_CONTEXT")

    # 前置校验首步外部输入：缺键直接报错并列出所需键名，不产生废弃会话
    problem = getattr(args, "problem", "") or ""
    required_inputs = chain_engine.first_step_external_inputs(args.name)
    missing = chain_engine.missing_start_inputs(args.name, initial_context, problem)
    if missing:
        problem_keys = sorted(set(required_inputs) & chain_engine.PROBLEM_DESCRIPTION_INPUTS)
        hint = f"provide missing keys via --context '{{\"key\":\"value\"}}'"
        if problem_keys:
            hint += f"; description-type keys {problem_keys} can also be satisfied by a non-empty --problem"
        return error(
            f"chain '{args.name}' step 1 requires inputs not provided: {missing}",
            code="MISSING_CONTEXT",
            data={"missing_inputs": missing,
                  "required_inputs": required_inputs,
                  "hint": hint})

    try:
        session = chain_engine.start_session(
            chain_name=args.name,
            project=getattr(args, "project", "") or "",
            problem_description=problem,
            initial_context=initial_context,
        )
        # 附上第一步信息
        first_step = chain_engine.get_current_step(session["session_id"])
        return success({
            "session": session,
            "first_step": first_step,
        }, message=f"排查会话已启动: {session['session_id']}")
    except (ValueError, chain_engine.ChainConfigError) as e:
        return error(str(e), code="CHAIN_NOT_FOUND")


def cmd_chain_provide(args) -> dict:
    """向已建会话补注入外部输入（平铺 merge 进 context 顶层）"""
    try:
        inputs = json.loads(args.inputs)
    except json.JSONDecodeError:
        return error(f"invalid JSON for --inputs: {args.inputs}", code="BAD_JSON")
    if not isinstance(inputs, dict):
        return error("--inputs must be a JSON object", code="BAD_JSON")

    try:
        session = chain_engine.provide_inputs(args.session, inputs)
    except ValueError as e:
        return error(str(e), code="SESSION_ERROR")

    # 注入后立即重校验当前步骤，让调用方确认输入已满足
    validation = chain_engine.validate_step(args.session, session["current_step"])
    return success({
        "session_id": session["session_id"],
        "status": session["status"],
        "injected_keys": sorted(inputs),
        "current_step": session["current_step"],
        "validation": validation,
    }, message=f"已注入输入: {sorted(inputs)}")


def cmd_chain_status(args) -> dict:
    """查看会话状态

    输出结构恒定：completed=true 时 current_step_detail 为 null（链路已走完），
    调用方应以 completed 字段判断，而非依赖 current_step_detail 非空。
    """
    session, err = _guarded_session_call(chain_engine.get_session, args.session)
    if err:
        return err
    if not session:
        return error(f"session '{args.session}' not found", code="NOT_FOUND")
    completed = session["status"] == "completed"
    # 契约：completed 时 current_step_detail 恒为 null（引擎完成最后一步后
    # current_step 保持在末步编号，不置 None 则会返回最后一步定义）
    current_step = None if completed else chain_engine.get_current_step(args.session)
    return success({
        "session": session,
        "completed": completed,
        "current_step": session["current_step"],
        "total_steps": session["total_steps"],
        "completed_count": len(session["completed_steps"]),
        "amendments_count": len(session.get("amendments", [])),
        "skipped_count": len(session.get("skipped_steps", [])),
        "skipped_steps": session.get("skipped_steps", []),
        "token_usage": chain_engine.get_token_usage(args.session),
        "current_step_detail": current_step,  # 链路 completed 时为 null
    }, message=f"会话状态: {session['status']}"
       + ("（全部步骤已完成）" if completed else f"（当前第 {session['current_step']} 步）"))


def cmd_chain_amend(args) -> dict:
    """回填更正已完成的步骤（追加 correction，不覆盖原始 outputs）"""
    outputs = {}
    if args.outputs:
        try:
            outputs = json.loads(args.outputs)
        except json.JSONDecodeError:
            return error(f"invalid JSON for --outputs: {args.outputs}", code="BAD_JSON")
        if not isinstance(outputs, dict):
            return error("--outputs must be a JSON object", code="BAD_JSON")

    evidence, parse_error = _parse_json_object(
        getattr(args, "evidence", None), "--evidence")
    if parse_error:
        return parse_error

    try:
        session = chain_engine.amend_step(
            session_id=args.session,
            target_step=args.step,
            outputs=outputs,
            summary=args.summary or "",
            evidence=evidence,
        )
        return success({
            "session_id": session["session_id"],
            "status": session["status"],
            "amended_step": args.step,
            "amendments_count": len(session.get("amendments", [])),
            "latest_amendment": session["amendments"][-1],
        }, message=f"step {args.step} 已回填更正（原 outputs 保留）")
    except chain_engine.EvidenceValidationError as e:
        return error(str(e), code="INVALID_EVIDENCE")
    except ValueError as e:
        return error(str(e), code="SESSION_ERROR")


def cmd_chain_step(args) -> dict:
    """查看当前步骤详情"""
    session, err = _guarded_session_call(chain_engine.get_session, args.session)
    if err:
        return err
    if session and session.get("status") == "completed":
        return error(f"session '{args.session}' is already completed", code="SESSION_COMPLETED")
    step = chain_engine.get_current_step(args.session)
    if not step:
        return error(f"session '{args.session}' not found or already completed",
                     code="NOT_FOUND")
    return success(step, message=f"当前步骤 {step.get('id', '?')}: {step.get('title', '')}")


def cmd_chain_complete(args) -> dict:
    """标记当前步骤完成，推进到下一步"""
    # 解析 outputs (JSON 字符串)
    outputs = {}
    if args.outputs:
        try:
            outputs = json.loads(args.outputs)
        except json.JSONDecodeError:
            return error(f"invalid JSON for --outputs: {args.outputs}", code="BAD_JSON")
        if not isinstance(outputs, dict):
            return error("--outputs must be a JSON object", code="BAD_JSON")

    evidence, parse_error = _parse_json_object(
        getattr(args, "evidence", None), "--evidence")
    if parse_error:
        return parse_error
    token_usage, parse_error = _parse_json_object(
        getattr(args, "token_usage", None), "--token-usage")
    if parse_error:
        return parse_error

    try:
        session = chain_engine.complete_step(
            session_id=args.session,
            outputs=outputs,
            summary=args.summary or "",
            evidence=evidence,
            token_usage=token_usage,
        )
        # 获取下一步信息
        next_step = None
        if session["status"] == "in_progress":
            next_step = chain_engine.get_current_step(args.session)
        return success({
            "session": {
                "session_id": session["session_id"],
                "status": session["status"],
                "current_step": session["current_step"],
                "total_steps": session["total_steps"],
                "completed_count": len(session["completed_steps"]),
            },
            "completed_step": session["completed_steps"][-1] if session["completed_steps"] else None,
            "skipped_steps": session.get("skipped_steps", []),
            "next_step": next_step,
        }, message=f"步骤已完成" + (f"，下一步: {next_step['title']}" if next_step else "，排查链路全部完成"))
    except chain_engine.EvidenceValidationError as e:
        return error(str(e), code="EVIDENCE_REQUIRED" if evidence is None else "INVALID_EVIDENCE")
    except chain_engine.TokenUsageValidationError as e:
        return error(str(e), code="BAD_TOKEN_USAGE")
    except ValueError as e:
        return error(str(e), code="SESSION_ERROR")


def cmd_chain_validate(args) -> dict:
    """验证是否可以执行目标步骤

    invalid 时返回 error 状态（进程退出码非零），保证 shell `&&` 链可阻断后续命令；
    data 中仍保留完整 validate 结果（含 valid 字段），供 agent 解析。
    """
    result, err = _guarded_session_call(
        chain_engine.validate_step, args.session, args.step)
    if err:
        return err
    if result["valid"]:
        return success(result, message="valid")
    return error(result.get("reason", "validation failed"),
                 code="VALIDATION_FAILED", data=result)


def cmd_chain_context(args) -> dict:
    """获取会话累积的上下文"""
    ctx, err = _guarded_session_call(chain_engine.get_context, args.session)
    if err:
        return err
    if not ctx:
        return error(f"session '{args.session}' not found", code="NOT_FOUND")
    return success(ctx, message="排查上下文")


def cmd_chain_report(args) -> dict:
    """生成报告落盘文件名与模板头部（CLI 不写文件，由调用方落盘）"""
    session, err = _guarded_session_call(chain_engine.get_session, args.session)
    if err:
        return err
    if not session:
        return error(f"session '{args.session}' not found", code="NOT_FOUND")
    if session.get("status") != "completed":
        return error(
            f"session '{args.session}' is not completed (status: {session.get('status')}); "
            "finish all steps before generating the report",
            code="SESSION_NOT_COMPLETED",
        )
    slug = (getattr(args, "slug", "") or "").strip()
    slug_error = chain_engine.validate_report_slug(slug)
    if slug_error:
        return error(slug_error, code="BAD_SLUG")
    try:
        report = chain_engine.build_report(args.session, slug)
    except chain_engine.ChainConfigError as e:
        # ChainConfigError 是 ValueError 子类，必须先于父类捕获，否则降级为 SESSION_ERROR
        return error(str(e), code="CHAIN_CONFIG_ERROR")
    except ValueError as e:
        return error(str(e), code="SESSION_ERROR")
    return success(report, message="报告文件名与模板头部已生成（CLI 不落盘，由调用方写入目标目录）")


def cmd_chain_usage(args) -> dict:
    """汇总会话 token 使用量；仅统计，不参与评分。"""
    usage, err = _guarded_session_call(chain_engine.get_token_usage, args.session)
    if err:
        return err
    if usage is None:
        return error(f"session '{args.session}' not found", code="NOT_FOUND")
    return success(usage, message="Token 使用量统计（不参与评分）")


def cmd_chain_sessions(args) -> dict:
    """列出最近的排查会话"""
    sessions = chain_engine.list_sessions(limit=args.limit)
    return success({"sessions": sessions, "total": len(sessions)},
                    message=f"共 {len(sessions)} 个会话")
