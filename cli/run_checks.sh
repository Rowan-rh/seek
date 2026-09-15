#!/bin/bash
# 仓库内 PR 机械检查入口：隔离 seek 状态，执行全量测试与离线 Harness 评测。
set -euo pipefail

CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$CLI_DIR/.." && pwd)"
TEMP_ROOT="$(mktemp -d -t seek-checks.XXXXXX)"
trap 'rm -rf "$TEMP_ROOT"' EXIT
export SEEK_HOME="$TEMP_ROOT/seek-home"
export PYTHONDONTWRITEBYTECODE=1

cd "$CLI_DIR"

echo "=== 1. 全量单元测试（隔离 SEEK_HOME） ==="
python3 -m unittest discover -s tests -v

echo ""
echo "=== 2. Harness 离线黑盒评测 ==="
python3 "$REPO_DIR/harness/run_evals.py"

echo ""
echo "=== 3. Agent 场景三层评测（replay） ==="
python3 "$REPO_DIR/harness/run_agent_evals.py"

echo ""
echo "=== 4. OpenSpec 校验 ==="
openspec validate --all --strict
openspec validate --archived --strict

echo ""
echo "=== 5. 裸 except grep ==="
if grep -REn "except\s*:" seek_cli/ tests/; then
    echo "ERROR: 发现裸 except 子句"
    exit 1
else
    echo "未发现裸 except 子句。"
fi
