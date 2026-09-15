# Tasks: add-chain-report-command

## 1. 引擎层（seek_cli/chain.py）

- [x] 1.1 `validate_report_slug(slug)`：小写 kebab-case 校验（≤80 字符），拒绝 `seek-report` 前缀/`YYYY-MM-DD` 日期前缀/`.md` 后缀/空值，返回错误信息或 None
- [x] 1.2 `build_report(session_id, slug)`：completed 会话校验 + slug 校验 + `get_report_template` 复用，返回 `{session_id, chain_name, report_date, slug, filename, template, header_markdown}`；不写任何文件
- [x] 1.3 `_render_template_header(template_path, session)`：读取模板首个 `---` 前的头部块，定向 replace `{session_id}/{chain_name}/{start_time}/{end_time}/{problem_description}`；模板不可读抛 ChainConfigError

## 2. 命令层与登记

- [x] 2.1 `commands/chain.py` 新增 `cmd_chain_report`：NOT_FOUND/SESSION_NOT_COMPLETED/BAD_SLUG/CHAIN_CONFIG_ERROR 错误映射，success 返回构造结果
- [x] 2.2 `cli.py` 注册 `chain report <session> --slug`（--slug 必填），docstring 用法补一行
- [x] 2.3 `capabilities.py` chain 组登记 report 子命令（参数与 parser 一致，契约测试自动校验）

## 3. 版本与文档

- [x] 3.1 `__init__.py` 版本 0.4.0→0.4.1 + CHANGELOG feat 条目
- [x] 3.2 `SKILL.md`：规则 5 增加文件名/头部由 `chain report` 生成的约束；执行协议 Step 8 同步；cli_version_ref → 0.4.1
- [x] 3.3 `references/command-reference.md` 标准排查协议补 `chain report` 用法

## 4. 测试与归档

- [x] 4.1 新增 `cli/tests/test_chain_report.py`：happy path（日期前缀/头部渲染/模板路径）、未完成会话拒绝、未知会话拒绝、非法 slug 拒绝（大小写/空格/前缀/日期/.md/超长/空）、ticket 链路 `{flowId}` 保留、命令层错误码
- [x] 4.2 全量测试通过（156/156，含新增 11 例）+ `python -m seek_cli version` 启动验证 + 端到端三场景实测（合法 slug/未完成会话/非法 slug）
- [x] 4.3 `openspec validate add-chain-report-command --strict` 通过
- [x] 4.4 `openspec archive add-chain-report-command --yes`，确认 `specs/chain-report-templates/spec.md` 合并结果
