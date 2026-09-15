# Delta: skill-install-consistency

## Purpose

定义 seek skill 安装/更新/状态命令（`seek skill install/update/status/uninstall`）的对齐判定与报告契约：任何"已对齐/已安装"结论必须如实可证伪——版本声明须与实际版本交叉校验，逐目录失败必须隔离且已完成结果不丢失，迁移各阶段失败必须准确标注，状态检查能力与其他子命令对称，源标识须反映工作区真实状态。

## ADDED Requirements

### Requirement: 版本声明一致性校验
系统 SHALL 在 `seek skill update` 与 `seek skill status` 中，将源码 `SKILL.md` frontmatter 的 `cli_version_ref` 与实际运行的 CLI 版本（`seek_cli.__version__`，与 `seek version` 同源）比较，并在输出 data 顶层给出 `version_consistency` 结构，含 `declared_cli_version`、`actual_cli_version` 与三态 `consistent`（`true` 一致 / `false` 漂移 / `null` 未声明）。版本漂移是告警而非失败：命令 MUST 保持 `status=ok` 与退出码 0，但 MUST 在 message 中追加不匹配告警。

#### Scenario: 声明与实际不一致时如实告警
- **WHEN** `SKILL.md` 声明 `cli_version_ref: 0.5.0` 而实际 `__version__` 为 `0.4.0`，执行 `seek skill update`
- **THEN** 输出 `status=ok`、退出码 0
- **AND** `data.version_consistency.consistent` 为 `false`
- **AND** message 包含"版本声明不匹配"类告警文本

#### Scenario: 一致时静默
- **WHEN** `cli_version_ref` 与实际 `__version__` 相同，执行 `seek skill update`
- **THEN** `data.version_consistency.consistent` 为 `true`，message 不含不匹配告警

#### Scenario: 未声明时不告警
- **WHEN** frontmatter 无 `cli_version_ref` 字段
- **THEN** `consistent` 为 `null`，不产生告警

### Requirement: 逐目录失败隔离
系统在执行 `seek skill update` 修复 `broken`/`foreign`/`not_found` 状态的安装点时，MUST 逐目录隔离异常：单个目录的修复失败（如权限错误）不得中断其余目录的处理，不得导致已完成结果丢失；失败目录的条目 MUST 标注 `status=error` 与错误信息，命令整体仍返回结构化结果。

#### Scenario: 第二目录失败不丢第一目录结果
- **GIVEN** 两个安装目录，第一个为指向别处的有效链接（foreign），第二个父目录无写权限
- **WHEN** 执行 `seek skill update`
- **THEN** 不抛出未捕获异常
- **AND** results 含两条：第一条 `status=fixed` 且链接已指向源码，第二条 `status=error` 含错误信息

### Requirement: 迁移阶段准确标注
系统迁移旧目录形态安装点（`status=directory`）时，MUST 区分失败阶段：压缩备份失败标注 `backup_failed`；备份成功但删除旧目录或建立链接失败标注 `migration_failed`，且该条目 MUST 携带已生成的 `backup` 路径供恢复。

#### Scenario: 备份成功但删除失败
- **GIVEN** 旧目录可读但不可删
- **WHEN** 执行 `seek skill update`
- **THEN** 条目 `status=migration_failed`（而非 `backup_failed`）
- **AND** 条目 `backup` 字段指向实际存在的 `.tar.gz` 文件

### Requirement: status 与其余子命令的 --dir 能力对称
`seek skill status` SHALL 接受 `--dir` 参数，语义与 `install`/`update`/`uninstall` 一致（指定时仅检查该目录）；命令能力声明（capabilities）MUST 与实际 parser 参数保持一致。`install --dir` 的帮助文案 MUST 如实反映默认目录为 `~/.qoder/skills` 与 `~/.qoderwork/skills` 两个。

#### Scenario: status 支持 --dir
- **WHEN** 执行 `seek skill status --dir /custom/skills`
- **THEN** 参数解析成功（退出码 0），仅报告该目录的安装状态

### Requirement: 源标识反映工作区状态
系统报告源码对齐标识时，`update`/`status` 输出 MUST 包含 `source_dirty` 字段：源码工作区存在未提交改动（含未跟踪文件）时为 `true`，干净为 `false`，无法判定（非 git 仓库等）为 `null`。

#### Scenario: 未提交改动被如实标记
- **GIVEN** 源码为 git 仓库，存在未提交的修改或未跟踪文件
- **WHEN** 执行 `seek skill status`
- **THEN** `data.source_dirty` 为 `true`
