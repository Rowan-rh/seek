"""调用链路查询命令 — 查询服务调用链路和 trace 信息"""

from pathlib import Path

from seek_cli import config
from seek_cli.integrations import sls_client
from seek_cli.output import success, error

# 工作区根目录
_WORKSPACE = Path(__file__).parent.parent.parent.parent.parent
_CALL_CHAIN_INDEX = _WORKSPACE / "call-chain-index.md"


def cmd_trace_call_chain(args) -> dict:
    """查询项目的调用链路文档"""
    proj = config.get_project(args.project)
    if not proj:
        return error(f"project '{args.project}' not found", code="NOT_FOUND")

    repo_path = proj.get("repoPath", "")
    if not repo_path:
        repo_path = str(_WORKSPACE / args.project)

    # 查找调用链路文档
    chain_file = Path(repo_path) / f"{args.project}-call-chain.md"
    if not chain_file.exists():
        # 尝试 workspace 根目录
        chain_file = _WORKSPACE / args.project / f"{args.project}-call-chain.md"

    if not chain_file.exists():
        return error(
            f"call-chain doc not found for '{args.project}'",
            code="NOT_FOUND",
            data={"expected_path": str(chain_file)},
        )

    # 读取并返回
    content = chain_file.read_text(encoding="utf-8")
    # 返回前 200 行作为预览（避免输出过大）
    lines = content.split("\n")
    preview = "\n".join(lines[:200])
    if len(lines) > 200:
        preview += f"\n\n... ({len(lines) - 200} more lines)"

    return success({
        "project": args.project,
        "file": str(chain_file),
        "total_lines": len(lines),
        "preview": preview,
    }, message=f"调用链路: {args.project}")


def cmd_trace_query(args) -> dict:
    """通过 traceId 查询 trace 信息（在 SLS 中搜索）"""
    proj = config.get_project(args.project)
    if not proj:
        return error(f"project '{args.project}' not found", code="NOT_FOUND")

    if not args.trace_id:
        return error("--trace-id is required", code="MISSING_ARG")

    # 构造 trace 查询
    # 不同服务的 trace ID 前缀不同（参考 service-topology.md）
    trace_query = f'"{args.trace_id}"'

    try:
        result = sls_client.query_by_config(
            project_config=proj,
            env=args.env,
            query=trace_query,
            time_range=args.time or "1h",
            max_results=args.max or 50,
        )
        return success({
            "project": args.project,
            "env": args.env,
            "trace_id": args.trace_id,
            "query_result": result,
        }, message=f"trace 查询完成: {result['count']} 条")
    except (RuntimeError, ValueError) as e:
        return error(str(e), code="SLS_QUERY_ERROR")


def cmd_trace_topology(args) -> dict:
    """查询服务拓扑关系"""
    topology_file = config.get_topology_file()
    if topology_file.exists():
        content = topology_file.read_text(encoding="utf-8")
        return success({
            "source": str(topology_file),
            "content": content[:5000],  # 前 5000 字符
            "truncated": len(content) > 5000,
        }, message="服务拓扑关系")
    else:
        return error(
            f"service topology file not found. "
            f"Set SEEK_TOPOLOGY_FILE, seek config set trace.topologyFile <path>, "
            f"or ~/.seek/config/trace.json#topologyFile",
            code="NOT_FOUND",
        )
