# Proposal: fix-harness-readiness-followup

## Why

CR 报告确认 `seek harness check` 在 `SEEK_HOME` 不可写时会先被版本标记写入触发未捕获异常，导致 stdout 为空并违反新建的 Harness 失败契约；同时错误日志降级和路径文案仍有收尾缺口。

## What Changes

- 将版本变更标记读写改为 best-effort，失败时仅向 stderr 提示，不阻断原命令。
- 错误日志写入失败时向 stderr 输出降级提示，同时保持原始命令响应不变。
- 为不可写 `SEEK_HOME` 增加真实 CLI 黑盒回归场景。
- 统一 parser、capabilities 中剩余的 `~/.seek` 路径文案为 `${SEEK_HOME:-~/.seek}`。
- 发布补丁版本并同步 Skill 版本声明。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-home-isolation`: 增加版本标记不可写时不得阻断业务命令的契约。
- `harness-readiness`: 离线评测必须覆盖不可写 seek home 的结构化失败路径。

## Impact

影响 `cli.py`、`error_log.py`、Harness runner/测试、capabilities/parser 文案、CHANGELOG 和 Skill 版本声明；不改变成功路径 JSON 结构。
