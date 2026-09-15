## Why

`seek init --verify` 当前只验证 A1 和 DMS，SLS 的 `verified` 永远为 false，却被纳入 `fully_ready` 聚合，导致即使可验证的接入全部成功，结果仍显示未完全就绪并重复提示 doctor。与此同时，错误日志上下文虽然已递归脱敏，但只限制叶子值长度，超大列表、字典或深层结构仍可能在错误路径中造成内存和日志文件无界增长。

## What Changes

- 明确并修正初始化验证状态的契约：`fully_ready` 不再因未执行的 SLS 活性验证而产生永远为假的结果；SLS 的本地配置状态与 doctor 活性验证状态分开表达。
- 保持默认 `seek init` 不访问外部服务；`--verify` 继续验证 A1/DMS，并以结构化字段准确反映可验证集成的结果。
- 为错误日志递归上下文增加总大小、节点数量和嵌套深度预算；超出预算时以稳定的截断标记替代剩余内容，同时继续递归脱敏。
- 增加回归测试，覆盖所有可验证集成成功、SLS 未执行活性验证、超大容器、深层嵌套及敏感键场景。

## Capabilities

### New Capabilities
- `error-log-context-bounds`: 定义错误日志上下文递归脱敏、总量预算和超限截断行为。

### Modified Capabilities
- `integration-initialization`: 修正 `seek init --verify` 的总体就绪字段和 SLS 验证状态表达，避免把未执行的活性检查误报为失败。

## Impact

- **CLI**：`seek init` / `seek init --verify` 的状态字段、`fully_ready` 和 `next_actions` 语义；保留现有命令参数和结构化输出兼容性。
- **错误日志**：`seek_cli/error_log.py` 的上下文序列化结果在超出预算时会被截断，敏感信息仍不得落盘。
- **测试**：更新初始化和可靠性测试，新增边界预算测试。
- **外部系统**：不新增默认外部调用；SLS 活性仍由 `seek doctor --liveness-window 24h` 负责，除非设计明确将其作为显式验证步骤。
