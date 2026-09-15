# Design: add-generic-report-template

## Context

- 现状：仅 `cli/chains/report-template.md` 一个模板，被 alert-ticket step 8 的 agentInstructions 硬编码引用；其余链路无模板。
- 仓库内 `cli/chains/default.json` 与 `cli/seek_cli/resources/chains/default.json` 是两份内容相同的链路定义：engine 运行时读 `resources/chains`（打包产物），`cli/chains/` 是仓库可编辑镜像，二者必须保持同步（现有约定）。
- chain 引擎已有「内置 → 用户覆盖」的资源分层模式（`_BUILTIN_CHAINS` vs `~/.seek/chains/default.json`），模板解析复用同一模式。

## Decisions

### D1: 模板存放位置
- 内置模板放 `cli/seek_cli/resources/chains/templates/{generic,ticket}.md`（engine 实际读取路径，随 setup.py package_data 打包）。
- `cli/chains/templates/` 保留同名镜像（与 default.json 双份约定一致），便于仓库内直接浏览/编辑；两份同步维护，测试校验一致性。
- 用户覆盖目录：`~/.seek/chains/templates/`。

### D2: 文件移动方式
`cli/chains/report-template.md` 用 `git mv` 到 `cli/chains/templates/ticket.md`（保留历史），内容不变；同步复制到 `resources/chains/templates/ticket.md`。

### D3: 引擎解析函数
`chain.py` 新增：
- `_BUILTIN_TEMPLATES = _PKG_ROOT / "resources" / "chains" / "templates"`
- `_USER_TEMPLATES = Path.home() / ".seek" / "chains" / "templates"`
- `get_report_template(chain_name) -> dict`：读取链路 `reportTemplate` 字段（缺省 `generic.md`），按 用户目录 → 内置目录 顺序查找；找不到时抛 `ChainConfigError`，错误信息含模板名与两个搜索路径（显式声明不存在的模板不静默回退；但缺省 generic.md 必然存在，随包分发）。
- `_validate_chain` 增加：`reportTemplate` 若存在必须是非空字符串。

### D4: 输出暴露
- `list_chains()` 每条目增加 `"reportTemplate": <文件名>`（静态声明/缺省值，不做文件解析，保持 list 轻量）。
- `get_context()` 增加 `"report_template": {"name": ..., "path": ...}`（做实际解析，保证 path 指向存在的文件；解析失败时输出 `{"name": ..., "error": ...}` 而非抛异常，避免 context 命令因模板问题阻断报告产出）。

### D5: generic.md 内容设计
从 ticket 模板抽离通用骨架，去掉 flowId/工单信息/相似工单/推荐联系人/转单等工单章节，保留并泛化：
1. 快速结论（故障型/咨询型二选一 → 泛化为「结论类型」占位，不强制工单分类字段）
2. 可复用排查路径与证据点（适用范围、标准路径、关键证据、分支决策映射、复用边界；保留通知类 deliveryState/运营商码分离的既有铁律作为"适用时"条款）
3. 排查过程（部署/日志/链路/DB/代码证据，按实际执行情况裁剪）
4. 根因分析（因果链 + 证据边界）
5. 修复建议（止血/根本修复/预防）
6. 未决事项（仅限权限/外部依赖，既有约束保留）
7. 更正记录（对应 chain amend）
头部元信息改为：排查会话 session_id、链路名、问题描述、时间窗。

### D6: 链路 agentInstructions 更新
- alert-ticket step 8：`cli/chains/report-template.md` 引用改为「chain context 输出的 report_template.path（即工单模板 ticket.md）」。
- 其余 6 条链路末步 agentInstructions 追加一句：报告按 `chain context` 输出的 `report_template.path` 指向的通用模板结构生成。
- 两份 default.json 同步修改。

## Risks / Trade-offs

- **双份模板镜像漂移**：新增测试校验 `cli/chains/templates/` 与 `resources/chains/templates/` 逐文件一致。
- **test_documentation.py 硬编码旧路径**：同步更新为 `cli/chains/templates/ticket.md` 与 `generic.md`。
- **SKILL.md 引用旧路径**：同步更新，保持 test_skill_references_exist 通过。
