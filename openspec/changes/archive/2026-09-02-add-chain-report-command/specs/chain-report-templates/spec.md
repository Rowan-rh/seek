# chain-report-templates Specification (Delta)

## ADDED Requirements

### Requirement: 报告文件名与头部构造入口
系统 SHALL 提供 `seek chain report <session> --slug <语义段>` 命令，对状态为 completed 的会话构造报告落盘要素：带产出日期前缀的文件名（`seek-report-YYYY-MM-DD-{slug}.md`，日期为命令执行日）、已填充机器可确定字段的模板头部 markdown 与报告模板解析结果（name/path）。该命令 MUST NOT 写入任何文件——落盘由调用方完成。

#### Scenario: completed 会话生成报告文件名与头部
- **WHEN** 对状态为 completed 的会话执行 `seek chain report <session> --slug "batch-560d6f3c-objectlist-empty"`
- **THEN** 返回 `filename` 形如 `seek-report-2026-09-02-batch-560d6f3c-objectlist-empty.md`（日期为当日）
- **AND** 返回 `header_markdown` 中 `{session_id}`/`{chain_name}`/`{start_time}`/`{end_time}`/`{problem_description}` 已替换为会话实际值，语义占位符（如 `{主题一句话}`、`{flowId}`）保持原样
- **AND** 返回 `template` 含解析后的模板名与绝对路径

#### Scenario: 未完成会话拒绝生成
- **WHEN** 对状态非 completed 的会话执行 `seek chain report`
- **THEN** 返回错误（`SESSION_NOT_COMPLETED`），不生成文件名与头部

#### Scenario: slug 格式非法拒绝
- **WHEN** `--slug` 为空、含大写/空格/下划线、超过 80 字符，或自带 `seek-report` 前缀、`YYYY-MM-DD` 日期前缀、`.md` 后缀
- **THEN** 返回错误（`BAD_SLUG`），错误信息说明合法格式（小写 kebab-case 语义段，如 `batch-560d6f3c-objectlist-empty`）

#### Scenario: 会话不存在
- **WHEN** 对不存在的会话 ID 执行 `seek chain report`
- **THEN** 返回错误（`NOT_FOUND`）
