# seek — 排查编排 CLI

AI agent 调用的命令行工具，覆盖部署查询、日志查询、调用链路、钉钉通信、工单分析和排查流程编排。

## 安装

```bash
cd cli
pip3 install -e .
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
```

## 首次初始化

安装 CLI 后先运行：

```bash
seek init
```

命令会检查 A1 CLI、DMS MCP 和 SLS AK/SK，并在 `next_actions` 中汇总缺失项与待验证动作。配置完成后可执行 `seek init --verify` 验证 A1 登录态和 DMS MCP 工具发现；SLS 的具体 project/logstore 权限与活性继续执行 `seek doctor --liveness-window 24h` 验证。`--verify` 返回的 `fully_ready` 只表示 init 自己负责的检查已完成，不代表 SLS 资源活性已验证。

- A1 CLI 配置指南：<https://a1.io.alibaba-inc.com/docs/guide/>
- DMS MCP 配置指南：<https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y>
- SLS：需要成对配置 AK/SK，推荐使用环境变量 `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`，也可使用 `seek config set`。

> 不要把真实 AK/SK、Token 或带密钥参数的 MCP URL 写入对话、日志或代码仓库。

## Qoder Skill 安装

```bash
ln -s "$(pwd)" ~/.qoder/skills/seek
```

## 目录结构

```
seek/
├── SKILL.md                # Qoder Skill 入口（教 agent 怎么用 CLI）
├── AGENT.md                # 开发规范与约束
├── references/             # 按需加载知识（排查作业 SOP、命令参考、调查模式、证据边界、应急响应模式）
├── openspec/               # 规格与变更（specs/ 现状，changes/ 进行中与归档）
├── scripts/seek_tmp.py     # 创建结构化仓库临时工作区
├── cli/                    # CLI 工具
│   ├── seek_cli/           # Python 包
│   │   ├── cli.py          # 主入口
│   │   ├── config.py       # 配置管理
│   │   ├── chain.py        # 排查链路引擎
│   │   ├── output.py       # 输出格式化
│   │   ├── commands/       # 命令实现
│   │   ├── integrations/   # 外部集成
│   │   └── resources/      # 运行时权威副本（setup.py 只打包这里，代码只读这里）
│   │       ├── config/
│   │       │   └── projects.json     # 项目配置
│   │       └── chains/
│   │           ├── default.json      # 排查链路定义
│   │           └── templates/        # 报告模板（generic.md / ticket.md）
│   ├── config/projects.json  # 项目配置（人类编辑镜像，须与 resources 副本一致）
│   ├── chains/               # 链路定义与报告模板（人类编辑镜像，同上）
│   ├── tests/                # 单测，含 test_doc_consistency.py 守护镜像与文档一致性
│   ├── TROUBLESHOOTING.md    # 按症状排错
│   ├── setup.py
│   └── README.md           # CLI 完整文档
└── README.md               # 本文件
```

项目清单以 `seek project list` 为准，链路清单以 `seek chain list` 为准，两者都不在文档里写死数量。

## 命令概览

| 命令 | 用途 | 集成 |
|------|------|------|
| `seek capabilities` | 输出所有命令能力清单 | 内置 |
| `seek init` | 检查并引导配置 A1 CLI、DMS MCP、SLS 凭据 | 内置 |
| `seek version` | 版本与 CHANGELOG | 内置 |
| `seek project` | 项目配置管理 | 内置 |
| `seek config` | 统一配置管理（seek.json） | 内置 |
| `seek doctor` | 配置体检（SLS 结构 + 实测存在性/活性） | 内置 + aliyun-log SDK |
| `seek harness` | Agent Harness 离线就绪检查 | 内置 |
| `seek deploy` | 部署信息查询 | A1 CLI |
| `seek sls` | SLS 日志查询 | aliyun-log SDK |
| `seek trace` | 调用链路查询 | 文档 + SLS |
| `seek chain` | 排查链路编排 | 内置引擎 |
| `seek dingtalk` | 钉钉聊天/文档/通讯录 | dws CLI |
| `seek ticket` | 云网络工单查询 | qt-expert API |
| `seek notify` | 通知触达查询（仅近 7 天） | roar noti-query |
| `seek db` | 数据库只读查询（双 backend） | DMS MCP + PyMySQL 本地直连 |
| `seek skill` | Skill 安装/状态/卸载 | 内置 |
| `seek errors` | 错误日志查看/清理 | 内置 |

命令组、子命令与参数的实时清单以 `seek capabilities` 为准。详见 [cli/README.md](cli/README.md)。

CI、沙箱或并行评测可在启动 CLI 前设置 `SEEK_HOME=/tmp/seek-case`，将 seek 自有配置、会话和日志与真实 `~/.seek` 隔离。

## 仓库临时工作区

仓库开发、Agent 分析或评审产生的临时文件统一放入 `.seek-tmp`，不要平铺在仓库根目录，也不要直接堆在 `.seek-tmp` 根目录。使用仓库 helper 创建一次任务的独立空间：

```bash
python3 scripts/seek_tmp.py create --slug review-cli-output
```

命令输出 JSON，固定路径模式为 `.seek-tmp/runs/YYYY-MM-DD/<run-id>/`，目录结构如下：

```text
.seek-tmp/
├── runs/
│   └── YYYY-MM-DD/
│       └── HHMMSSZ-task-slug-shortid/
│           ├── manifest.json
│           ├── inputs/
│           ├── work/
│           ├── outputs/
│           └── logs/
└── cache/
```

`.seek-tmp/` 已整体忽略。需要提交或交付的正式产物必须从 `outputs/` 移至仓库约定目录。该目录不替代 `${SEEK_HOME:-~/.seek}`、系统临时目录，或原子写时与目标文件同目录的 `.filename-*.tmp`。完整规则见 [`AGENT.md`](AGENT.md)。

## 集成

| 集成 | 类型 | 认证 | 命令 |
|------|------|------|------|
| A1 CLI | subprocess | `a1 auth login`（[指南](https://a1.io.alibaba-inc.com/docs/guide/)） | deploy |
| aliyun-log SDK | Python SDK | `~/.aliyun/config.json` | sls, trace |
| dws CLI | subprocess | QoderWork 内置 | dingtalk |
| qt-expert API | HTTP | 无需(内网) | ticket |
| DMS MCP | stdio JSON-RPC | `~/.qoderwork/mcp.json`（[指南](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y)） | db |

## Agent 接入

- **能力发现**：`seek capabilities` 输出实时命令 JSON schema，是参数和子命令的权威来源
- **Qoder Skill**：[`SKILL.md`](SKILL.md) 只承载显式触发规则、排查工作流和不可绕过的执行契约
- **按需知识**：[`references/`](references/) 存放证据边界、调查模式和命令参考，按当前场景加载
- **排查链路**：`chain` 命令组提供步骤指引、约束检查、结构化证据、上下文累积和 token 使用量统计（不参与评分）
- **故障排查**：[`cli/TROUBLESHOOTING.md`](cli/TROUBLESHOOTING.md) 按症状记录依赖、配置和错误码处理

文档职责不要交叉复制：仓库导航看本 README，CLI 静态用法看 [`cli/README.md`](cli/README.md)，运行时链路约束以 `cli/chains/default.json` 和 `seek chain step` 为准。
