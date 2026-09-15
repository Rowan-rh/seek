#!/usr/bin/env python3
"""Run versioned Agent scenarios in deterministic replay or external live mode."""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CLI_DIR = _ROOT / "cli"
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

from seek_cli import agent_eval  # noqa: E402

_DEFAULT_SCENARIOS = _ROOT / "harness" / "scenarios" / "v1.json"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=str(_DEFAULT_SCENARIOS),
                        help="版本化 Agent 场景 JSON 文件")
    parser.add_argument("--agent-command",
                        help="真实 Agent runner 命令；省略时使用场景 replay")
    parser.add_argument("--timeout", type=int, default=120,
                        help="每个 live 场景的超时秒数")
    parser.add_argument("--scenario", action="append", dest="scenario_ids",
                        help="仅运行指定场景，可重复")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenario_set = agent_eval.load_scenario_set(args.scenarios)
        report = agent_eval.run_scenarios(
            scenario_set,
            agent_command=args.agent_command,
            timeout=args.timeout,
            scenario_ids=args.scenario_ids,
        )
    except agent_eval.AgentEvalConfigError as exc:
        report = {
            "status": "error",
            "error": {"code": "AGENT_EVAL_CONFIG_ERROR", "message": str(exc)},
        }
    except Exception as exc:
        report = {
            "status": "error",
            "error": {"code": "AGENT_EVAL_INTERNAL_ERROR", "message": str(exc)},
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
