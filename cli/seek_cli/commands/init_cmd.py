"""seek init — inspect and guide external integration setup."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from seek_cli import settings
from seek_cli.output import success
from seek_cli.plugins import get_provider


_alibaba = get_provider("alibaba")
a1_client = _alibaba.service("a1")
dms_client = _alibaba.service("dms")
sls_client = _alibaba.service("sls")

DMS_MCP_GUIDE_URL = dms_client.DMS_MCP_GUIDE_URL
A1_CLI_GUIDE_URL = a1_client.A1_CLI_GUIDE_URL
# A1 CLI 登录凭据落盘于 auth.yaml（历史误写为 config.yaml，导致已登录仍被判为未配置）
A1_CONFIG = Path.home() / ".config" / "a1" / "auth.yaml"


def _command_available(command: str) -> bool:
    """Return whether an executable command can be resolved locally."""
    if not command:
        return False
    expanded = Path(command).expanduser()
    if expanded.is_absolute() or "/" in command:
        return expanded.is_file() and os.access(str(expanded), os.X_OK)
    return shutil.which(command) is not None


def _a1_status(verify: bool) -> dict:
    """Inspect A1 CLI installation and optionally verify authentication."""
    executable = shutil.which("a1")
    result = {
        "name": "A1 CLI",
        "required_for": ["deploy", "Aone application/repository lookup"],
        "documentation": A1_CLI_GUIDE_URL,
        "configured": bool(executable and A1_CONFIG.exists()),
        "verified": False,
        "config_path": str(A1_CONFIG),
        "verify_command": "a1 auth whoami --format json",
        "setup_steps": [
            "打开 A1 CLI 使用指南并按当前平台说明完成安装",
            "执行 a1 auth login 完成登录",
            "执行 a1 auth whoami --format json 验证登录态",
        ],
    }
    if not executable:
        result.update(status="missing", detail="未在 PATH 中找到 a1")
        return result
    result["executable"] = executable
    if not verify and not A1_CONFIG.exists():
        result.update(status="needs_auth", detail="A1 CLI 已安装，但未发现默认登录配置")
        return result
    if not verify:
        result.update(status="configured_unverified", detail="已安装并发现登录配置；登录态未主动验证")
        return result
    try:
        completed = subprocess.run(
            [executable, "auth", "whoami", "--format", "json", "--no-update-check"],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result.update(status="verification_failed", configured=False, detail="A1 登录态检查未完成")
        return result
    if completed.returncode == 0:
        # 登录态以 whoami 实测为准：成功即视为就绪，覆盖仅凭文件探测得到的 configured
        result.update(status="ready", verified=True, configured=True, detail="A1 CLI 已安装且登录态有效")
    else:
        result.update(status="needs_auth", configured=False, detail="A1 CLI 已安装，但登录态验证失败；请重新登录")
    return result


def _load_dms_server() -> tuple:
    """Load the configured DMS MCP server without exposing its environment."""
    path = dms_client._MCP_CONFIG
    if not path.exists():
        return None, "missing", f"配置文件不存在: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, "invalid", f"配置文件不可读或 JSON 非法: {type(exc).__name__}"
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
        return None, "invalid", "配置缺少 mcpServers 对象"
    server = data["mcpServers"].get("dms-mcp-server")
    if not isinstance(server, dict):
        return None, "missing", "配置缺少 mcpServers.dms-mcp-server"
    command = server.get("command")
    args = server.get("args", [])
    if not isinstance(command, str) or not command.strip():
        return None, "invalid", "dms-mcp-server.command 必须是非空字符串"
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        return None, "invalid", "dms-mcp-server.args 必须是字符串数组"
    return server, "configured", "DMS MCP 配置结构有效"


def _dms_status(verify: bool) -> dict:
    """Inspect DMS MCP configuration and optionally call tools/list."""
    server, status, detail = _load_dms_server()
    result = {
        "name": "DMS MCP",
        "required_for": ["db queries for managed/production databases"],
        "documentation": DMS_MCP_GUIDE_URL,
        "config_path": str(dms_client._MCP_CONFIG),
        "configured": status == "configured",
        "verified": False,
        "verify_command": "seek db tools",
        "setup_steps": [
            "打开集团版 DMS MCP 使用指南并完成授权",
            f"将 dms-mcp-server 配置写入 {dms_client._MCP_CONFIG}",
            "执行 seek db tools 验证 MCP 启动、认证和工具发现",
        ],
    }
    if server is None:
        result.update(status=status, detail=detail)
        return result
    command = server["command"].strip()
    if not _command_available(command):
        result.update(
            status="missing_runtime",
            configured=False,
            detail="DMS MCP 启动命令不可用或不在 PATH",
        )
        return result
    if not verify:
        result.update(status="configured_unverified", detail="配置存在且启动命令可用；尚未验证 MCP 连接")
        return result
    client = dms_client.DmsMcpClient()
    try:
        tools = client.list_tools()
    except Exception:
        result.update(
            status="verification_failed",
            configured=False,
            detail="DMS MCP tools/list 验证失败；请按文档检查授权、网络和配置",
        )
    else:
        result.update(
            status="ready",
            verified=True,
            detail=f"DMS MCP 可用，共发现 {len(tools)} 个工具",
        )
    finally:
        client.close()
    return result


def _sls_credential_source() -> str:
    """Return the active SLS credential source category without secret values."""
    if (os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
            and os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")):
        return "environment"
    if (settings.get_setting("sls.access_key_id")
            and settings.get_setting("sls.access_key_secret")):
        return "seek_config"
    if sls_client._CREDENTIALS_FILE.exists():
        try:
            legacy = json.loads(sls_client._CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            legacy = {}
        if (isinstance(legacy, dict) and legacy.get("access_key_id")
                and legacy.get("access_key_secret")):
            return "legacy_seek_credentials"
    for path in sls_client._ALIYUN_CONFIGS:
        if not path.exists():
            continue
        try:
            aliyun = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        profiles = aliyun.get("profiles", []) if isinstance(aliyun, dict) else []
        current = aliyun.get("current", "") if isinstance(aliyun, dict) else ""
        for profile in profiles if isinstance(profiles, list) else []:
            if not isinstance(profile, dict):
                continue
            selected = profile.get("name") == current or (not current and profile is profiles[0])
            if (selected and profile.get("access_key_id")
                    and profile.get("access_key_secret")):
                return "aliyun_cli_profile"
    return "unknown"


def _sls_status() -> dict:
    """Inspect SLS SDK and credential availability without exposing secrets."""
    result = {
        "name": "SLS",
        "required_for": ["sls", "trace query", "doctor live checks"],
        "documentation": None,
        "configured": False,
        "verified": False,
        "verification_scope": "doctor",
        "verify_command": "seek doctor --liveness-window 24h",
        "setup_steps": [
            "准备具备最小只读权限的 SLS AccessKey ID 和 AccessKey Secret",
            "推荐通过环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 配置",
            "也可执行 seek config set sls.access_key_id '<AK>' 与 seek config set sls.access_key_secret '<SK>'",
            "执行 seek doctor --liveness-window 24h 验证目标 project/logstore 权限与活性",
        ],
        "security_note": "不要在对话、日志、提交记录或共享终端历史中粘贴真实 AK/SK",
    }
    if not sls_client.SDK_AVAILABLE:
        result.update(status="missing_dependency", detail="未安装 aliyun-log Python SDK")
        return result
    try:
        sls_client._get_credentials()
    except Exception:
        result.update(status="missing_credentials", detail="未找到成对可用的 SLS AK/SK")
        return result
    result.update(
        status="configured",
        configured=True,
        detail="SLS SDK 与凭据已配置；具体资源访问请运行 seek doctor 验证",
        credential_source=_sls_credential_source(),
    )
    return result


def build_initialization_report(verify: bool = False) -> dict:
    """Build the integration setup report.

    Args:
        verify: Whether to run read-only A1 and DMS connectivity checks.

    Returns:
        Structured setup status without credential values.
    """
    integrations = [
        _a1_status(verify),
        _dms_status(verify),
        _sls_status(),
    ]
    ready = all(item["configured"] for item in integrations)
    # SLS resource liveness is intentionally owned by doctor, not init.
    fully_ready = verify and all(
        item["configured"] and (item["verified"] or item.get("verification_scope") == "doctor")
        for item in integrations
    )
    next_actions = []
    for item in integrations:
        if not item["configured"]:
            next_actions.extend(
                f"{item['name']}: {step}" for step in item["setup_steps"]
            )
        elif not item["verified"] and item.get("verification_scope") != "doctor":
            next_actions.append(f"{item['name']}: {item['verify_command']}")
    return {
        "ready": ready,
        "fully_ready": fully_ready,
        "verification_requested": verify,
        "integrations": integrations,
        "next_actions": next_actions,
        "security": [
            "仅使用最小权限账号或 RAM 用户",
            "不要把 AK/SK、Token 或带密钥的 MCP URL 写入对话、日志或代码仓库",
            "初始化命令只检查状态，不自动写入凭据或修改 MCP 配置",
        ],
    }


def cmd_init(args) -> dict:
    """Return setup status and actionable onboarding guidance."""
    verify = bool(getattr(args, "verify", False))
    data = build_initialization_report(verify=verify)
    ready_count = sum(item["configured"] for item in data["integrations"])
    message = f"初始化检查完成: {ready_count}/{len(data['integrations'])} 项本地接入已就绪"
    if verify:
        verified_count = sum(item["verified"] for item in data["integrations"])
        message += f"，{verified_count} 项已完成 init 在线验证"
        if any(item.get("verification_scope") == "doctor" for item in data["integrations"]):
            message += "；SLS 资源活性请执行 seek doctor --liveness-window 24h 验证"
    return success(data, message=message)
