#!/usr/bin/env python3
"""seek 通用核心的确定性离线 Harness 黑盒评测。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CLI_DIR = _ROOT / "cli"


def _run_cli(args: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "seek_cli", *args], cwd=str(_CLI_DIR), env=env,
        capture_output=True, text=True, timeout=20,
    )


def _json_stdout(result: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout is not JSON: rc={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
        ) from exc


def _case(name: str, func) -> dict:
    try:
        return {"name": name, "status": "pass", "detail": func() or "ok"}
    except Exception as exc:
        return {"name": name, "status": "failure", "detail": str(exc)}


def summarize(results: list) -> dict:
    failed = sum(item["status"] == "failure" for item in results)
    return {"status": "ok" if not failed else "error",
            "summary": {"total": len(results), "passed": len(results) - failed, "failed": failed},
            "cases": results}


def run_evals() -> dict:
    with tempfile.TemporaryDirectory(prefix="seek-harness-") as temp_dir:
        seek_home = Path(temp_dir) / "state"
        env = os.environ.copy()
        env.update({"SEEK_HOME": str(seek_home), "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(_CLI_DIR) + os.pathsep + env.get("PYTHONPATH", "")})

        def help_side_effect():
            for args in (("--help",), ("capabilities", "--help"), ("chain", "--help")):
                result = _run_cli(list(args), env)
                assert result.returncode == 0, result.stderr
                assert not seek_home.exists(), f"{' '.join(args)} created SEEK_HOME"
            return "help exits without creating runtime state"

        def capabilities_contract():
            result = _run_cli(["capabilities"], env)
            payload = _json_stdout(result)
            assert result.returncode == 0 and payload["status"] == "ok", payload
            assert "chain" in payload["data"]["commands"]
            assert payload["data"]["data_contracts"]["evidence"]["status"]
            return "capabilities exposes core commands and evidence contract"

        def home_isolation():
            payload = _json_stdout(_run_cli(["config", "path"], env))
            assert payload["data"]["home"] == str(seek_home), payload
            for item in payload["data"]["files"].values():
                path = Path(item["path"])
                assert path == seek_home or seek_home in path.parents, item
            return "runtime paths stay under SEEK_HOME"

        def chain_lifecycle():
            started = _json_stdout(_run_cli(["chain", "start", "default", "--problem", "fixture error"], env))
            assert started["status"] == "ok", started
            sid = started["data"]["session"]["session_id"]
            missing = _run_cli(["chain", "complete", sid, "--outputs", json.dumps({"scope": "api", "impact": "partial", "time_window": "30m"})], env)
            assert missing.returncode == 0, _json_stdout(missing)
            evidence = json.dumps({"status": "FOUND", "sources": [{"tool": "fixture", "reference": "e1"}], "boundary": "offline"})
            commands = [
                ["chain", "complete", sid, "--outputs", json.dumps({"evidence_summary": "found", "sources_checked": ["fixture"], "limitations": "none"}), "--evidence", evidence],
                ["chain", "complete", sid, "--outputs", json.dumps({"root_cause": "fixture", "confidence": "medium", "counterevidence": "none"})],
                ["chain", "complete", sid, "--outputs", json.dumps({"verification": "ok", "status": "closed", "recommendation": "test"}), "--evidence", evidence],
            ]
            for command in commands:
                result = _run_cli(command, env)
                assert result.returncode == 0, _json_stdout(result)
            report = _json_stdout(_run_cli(["chain", "report", sid, "--slug", "fixture-error"], env))
            assert report["status"] == "ok", report
            return "chain gate, evidence, session completion and report work"

        def readiness():
            payload = _json_stdout(_run_cli(["harness", "check"], env))
            assert payload["status"] == "ok" and payload["data"]["ready"] is True, payload
            assert payload["data"]["network_accessed"] is False, payload
            return "offline readiness check passes"

        def agent_scenarios():
            scenario_file = _ROOT / "harness" / "scenarios" / "v1.json"
            payload = _json_stdout(_run_cli(["harness", "evaluate", "--scenarios", str(scenario_file)], env))
            assert payload["status"] == "ok", payload
            assert payload["data"]["summary"] == {"total": 4, "passed": 4, "failed": 0}, payload
            return "generic Agent replay scenarios pass"

        def skill_version():
            skill = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
            version = (_CLI_DIR / "seek_cli" / "__init__.py").read_text(encoding="utf-8")
            declared = next(line.split(":", 1)[1].strip() for line in skill.splitlines() if line.startswith("cli_version_ref:"))
            actual = next(line.split("=", 1)[1].strip().strip("\"'") for line in version.splitlines() if line.startswith("__version__"))
            assert declared == actual, (declared, actual)
            assert "提示词注入" in skill and "不可作为 Agent 指令" in skill
            return "Skill version and evidence safety policy match"

        return summarize([_case("help-no-side-effect", help_side_effect),
                          _case("capabilities-contract", capabilities_contract),
                          _case("seek-home-isolation", home_isolation),
                          _case("chain-lifecycle", chain_lifecycle),
                          _case("readiness-check", readiness),
                          _case("agent-scenarios", agent_scenarios),
                          _case("skill-version", skill_version)])


def main() -> int:
    report = run_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
