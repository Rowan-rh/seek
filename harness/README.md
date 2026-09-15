# Agent Harness

Harness 用脱敏场景评估 Agent 是否遵守 seek 的通用排查协议，主要检查三层：

1. 协议：是否输出合法 JSON、是否尊重 Chain gate。
2. 轨迹：是否按步骤执行、是否调用声明的工具、是否避免重复或越权动作。
3. 报告：是否包含证据、边界、引用、根因置信度和可执行建议。

运行：

```bash
cd cli
seek harness check
seek harness evaluate
```

场景文件位于 `harness/scenarios/v1.json`，只描述通用问题和抽象 Provider 能力，不包含真实平台、账号或业务数据。
