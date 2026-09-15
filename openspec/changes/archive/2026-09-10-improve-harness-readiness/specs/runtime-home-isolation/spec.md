# Delta: runtime-home-isolation

## Purpose

定义 seek 可变运行时状态的统一根目录覆盖能力，使 CLI 能在 CI、沙箱和 Agent Harness 中隔离运行，同时保持现有用户默认路径兼容。

## ADDED Requirements

### Requirement: SEEK_HOME 统一覆盖可变状态根目录
系统 SHALL 在进程启动时读取 `SEEK_HOME`。当该变量为非空路径时，项目配置、统一配置、旧版兼容配置、用户链路覆盖、报告模板覆盖、会话、错误日志、性能日志和版本标记等原位于 `~/.seek` 的内容 MUST 全部改为位于 `SEEK_HOME` 下的相同相对路径；未设置时 SHALL 继续使用 `~/.seek`。

#### Scenario: Harness 使用隔离目录
- **WHEN** 以 `SEEK_HOME=/tmp/seek-case` 启动 CLI 并创建 chain session
- **THEN** session 和锁文件只写入 `/tmp/seek-case/sessions`
- **AND** 不在真实 `~/.seek/sessions` 中产生文件

#### Scenario: 默认路径保持兼容
- **WHEN** 未设置 `SEEK_HOME`
- **THEN** seek 可变状态仍从 `~/.seek` 读取并写入

### Requirement: 帮助命令无持久化副作用
CLI SHALL 在完成参数解析后再执行版本变更记录逻辑，因此仅请求根命令或子命令 `--help` 时 MUST NOT 创建 seek home、版本文件、session 或日志文件。

#### Scenario: 根帮助不创建目录
- **WHEN** 在不存在的隔离 `SEEK_HOME` 下执行 `python -m seek_cli --help`
- **THEN** 命令退出码为 0
- **AND** 隔离目录仍不存在
