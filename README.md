# seek

`seek` 是一个面向 Agent 的通用问题排查编排核心：用可验证的 Chain 组织步骤，用 Session 保存上下文，用 Evidence 记录来源边界，用插件接入日志、指标、部署、数据库或业务系统。

项目本身不内置任何云厂商、告警平台或通知平台实现。具体数据源由独立插件提供，核心可以在本地、CI、企业内网或不同云环境中复用。

## 快速开始

```bash
cd cli
python3 -m pip install -e .
seek capabilities
seek plugin list
seek chain list
seek chain start default --problem "接口在某个时间窗口内持续返回 5xx"
```

`chain start` 会创建会话并返回首个步骤。之后按步骤执行外部工具，把结果作为结构化 outputs 和 evidence 提交：

```bash
seek chain step <session_id>
seek chain complete <session_id> \
  --outputs '{"scope":"checkout-api","impact":"部分请求失败","time_window":"最近 30 分钟"}'
seek chain context <session_id>
seek chain validate <session_id> --step 1
seek chain report <session_id>
```

## 核心设计

- Chain：JSON 定义步骤、输入、输出、前置约束和证据要求。
- Session：持久化一次排查的进度、上下文、证据和 token 使用量。
- Evidence：每条证据带状态、来源引用、验证边界和失败原因。
- Report：根据模板生成可复用的 Markdown 报告。
- Plugin：通过 Python entry point 发现外部 Provider 和 CLI 命令。
- Harness：用脱敏场景验证 Agent 是否遵守链路门禁、证据协议和报告闭环。

## 插件

插件通过 `seek.plugins` entry point 注册：

```toml
[project.entry-points."seek.plugins"]
acme = "acme_seek_plugin:plugin"
```

插件可以声明 Provider 能力、配置 schema、CLI 子命令和自定义 Chain。核心只负责发现、展示和编排，不读取或保存插件凭据。插件开发契约见 [`PLUGIN.md`](PLUGIN.md)。

## 项目配置

核心只保存项目名称、描述、仓库路径和通用 metadata：

```bash
seek project add checkout --desc "Checkout service" --repo /workspace/checkout \
  --metadata '{"owner":"platform"}'
seek project show checkout
```

Provider 的 endpoint、凭据和资源映射应由对应插件管理，不进入核心项目配置。

## Agent 集成

`SKILL.md` 是 Agent 使用 seek 的入口，内容只描述通用排查协议：

```bash
seek skill install
```

## 开发与验证

```bash
cd cli
python3 -m pytest -q
./run_checks.sh
```

仓库内测试只验证核心协议、插件发现、配置隔离、报告生成和 Harness，不依赖外部账号或特定平台。

## 目录结构

```text
cli/seek_cli/                 Python 核心与 CLI
cli/seek_cli/resources/       内置 Chain、模板和空项目配置
cli/chains/                   可复制到用户目录的示例配置
harness/                      Agent 场景评估
references/                   通用设计与取证约定
PLUGIN.md                     插件开发契约
SKILL.md                      Agent 使用说明
```

## 许可证

Apache-2.0
