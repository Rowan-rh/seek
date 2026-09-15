# Tasks: add-generic-report-template

## 1. 模板文件

- [x] 1.1 `git mv cli/chains/report-template.md cli/chains/templates/ticket.md`（内容不变）
- [x] 1.2 新建 `cli/chains/templates/generic.md`：通用排查报告模板（章节见 design D5；不得含 flowId/questionTitle 等工单占位符）
- [x] 1.3 将两份模板同步复制到 `cli/seek_cli/resources/chains/templates/`

## 2. chain 引擎

- [x] 2.1 `chain.py`：新增 `_BUILTIN_TEMPLATES` / `_USER_TEMPLATES` 常量与 `get_report_template(chain_name)` 解析函数（用户目录优先，缺失抛 ChainConfigError 且含搜索路径）
- [x] 2.2 `chain.py`：`_validate_chain` 校验 `reportTemplate` 若非缺失必须为非空字符串
- [x] 2.3 `chain.py`：`list_chains()` 条目增加 `reportTemplate`；`get_context()` 增加 `report_template`（解析失败降级为 error 字段不抛异常）

## 3. 链路定义

- [x] 3.1 `cli/chains/default.json`：alert-ticket 增加 `"reportTemplate": "ticket.md"`；alert-ticket step 8 与其他 6 条链路末步 agentInstructions 指向 `chain context` 输出的 `report_template.path`
- [x] 3.2 同步修改 `cli/seek_cli/resources/chains/default.json` 保持一致

## 4. 打包与测试

- [x] 4.1 `setup.py` package_data 增加 `resources/chains/templates/*.md`
- [x] 4.2 新建 `cli/tests/test_report_templates.py`：镜像一致性、generic 必备章节且无工单占位符、模板解析（缺省回退/显式绑定/缺失报错/用户覆盖优先）、list_chains 与 get_context 输出字段
- [x] 4.3 更新 `cli/tests/test_documentation.py`：模板路径引用改为 `cli/chains/templates/ticket.md` 与 `cli/chains/templates/generic.md`

## 5. 文档与验证

- [x] 5.1 `SKILL.md`：报告产出指引改为按 `report_template.path` 读取模板，更新文件引用表
- [x] 5.2 `cli/README.md`：更新模板说明与 alert-ticket 描述
- [x] 5.3 运行 `python -m unittest discover cli/tests` 全绿
- [x] 5.4 `openspec validate --strict add-generic-report-template` 通过
