# seek CLI 故障排查

## 1. 先确认安装和能力

```bash
seek version
seek capabilities
seek plugin list
```

如果插件没有出现在列表中，确认它已经安装到当前 Python 环境，并声明了 `seek.plugins` entry point。核心不会自动安装或猜测插件依赖。

## 2. Chain 无法启动

```bash
seek chain list
seek chain show default
seek chain start default --problem "具体问题描述"
```

问题描述应包含现象、对象和时间窗口。自定义 Chain 放在用户 seek home 的 `chains/default.json`，文件必须是合法 JSON，并满足 Chain 的输入、输出和步骤约束。

## 3. 步骤无法完成

先查看当前步骤和上下文：

```bash
seek chain step <session_id>
seek chain context <session_id>
```

`outputs` 只能包含当前步骤声明的字段。需要证据的步骤必须传入完整 Evidence；当查询无数据或工具报错时，使用对应状态并填写 `reason` 和 `boundary`。

## 4. 报告无法生成

```bash
seek chain validate <session_id>
seek chain report <session_id>
```

先修复校验输出中的缺失输入、步骤顺序或证据边界。自定义报告模板只能是单个安全文件名，并放在用户 Chain 模板目录。

## 5. Harness 验证

```bash
seek harness check
seek harness evaluate
```

Harness 默认使用仓库内脱敏场景，不访问外部服务。若使用 `--agent-command`，该命令的 stdout 必须输出符合 `agent_eval` 结果协议的 JSON。

## 6. 配置和日志

```bash
seek config path
seek config show
seek errors list
seek perf report
```

核心只管理通用配置和本地会话；Provider 的凭据、endpoint 和资源映射应查看对应插件文档。
