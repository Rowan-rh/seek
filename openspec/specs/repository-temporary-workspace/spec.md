# repository-temporary-workspace Specification

## Purpose
为仓库内 Agent 与开发任务提供统一、可识别且可整体清理的临时工作区，避免报告、日志、截图和中间数据平铺堆积或与正式交付物混淆。

## Requirements

### Requirement: 临时产物按运行单元隔离
仓库内由 Agent 或开发辅助流程产生、且不属于正式源码或交付物的临时产物 MUST 写入 `.seek-tmp/runs/YYYY-MM-DD/<run-id>/`。`.seek-tmp` 根目录 MUST NOT 直接存放任务产物。

#### Scenario: 创建一次临时任务运行目录
- **WHEN** 为任务 `review-cli-output` 创建临时工作区
- **THEN** 系统在 `.seek-tmp/runs/YYYY-MM-DD/` 下创建唯一运行目录
- **AND** 不在 `.seek-tmp` 根目录直接创建任务文件

### Requirement: 运行目录使用固定结构
每个运行目录 MUST 包含 `inputs/`、`work/`、`outputs/`、`logs/` 四个目录以及 `manifest.json`。运行标识 MUST 由 UTC 时间、规范化任务 slug 和防冲突短标识组成。

#### Scenario: 检查新运行目录结构
- **WHEN** 临时工作区创建成功
- **THEN** 四个阶段目录和 `manifest.json` 均存在
- **AND** manifest 记录 schema 版本、运行标识、任务 slug、UTC 创建时间、状态和各阶段相对路径

#### Scenario: 同秒创建同名任务
- **WHEN** 同一秒内为相同任务创建多个临时工作区
- **THEN** 每次创建得到不同的运行目录
- **AND** 已存在的运行目录及内容不会被覆盖

### Requirement: 提供机器可读的创建入口
仓库 MUST 提供无需第三方依赖的临时工作区创建入口。创建成功时 MUST 向 stdout 输出 JSON，并至少返回运行目录及四个阶段目录；参数无效或创建失败时 MUST 返回非零退出码且不得留下不完整运行目录。

#### Scenario: Agent 创建工作区
- **WHEN** Agent 使用合法任务 slug 调用创建入口
- **THEN** 命令返回退出码 0
- **AND** stdout 可解析为 JSON 并包含所创建目录的路径

#### Scenario: Agent 使用非法任务 slug
- **WHEN** Agent 使用无法规范化为非空文件名的任务 slug
- **THEN** 命令返回非零退出码和明确错误信息
- **AND** 不创建运行目录

### Requirement: 临时工作区不进入版本控制
仓库 MUST 忽略 `.seek-tmp/` 的全部运行产物。开发规范 MUST 明确正式交付物需要移至其约定目录，且不得长期保存在 `.seek-tmp` 中。

#### Scenario: 创建临时工作区后检查 Git 状态
- **WHEN** 在仓库中创建 `.seek-tmp` 运行目录和文件
- **THEN** 这些文件不会作为未跟踪文件出现在 Git 状态中

### Requirement: 不改变运行时与原子写临时文件语义
`.seek-tmp` 规范 MUST NOT 替代 `${SEEK_HOME:-~/.seek}` 中的 CLI 运行状态、操作系统临时目录，或目标文件同目录下用于原子替换的临时文件。

#### Scenario: 保存需要原子替换的配置
- **WHEN** seek CLI 使用临时文件加 `os.replace` 保存配置
- **THEN** 临时文件仍创建在目标文件所在目录以保持同文件系统原子替换
- **AND** 不重定向到仓库 `.seek-tmp`
