# Delta: emergency-case-patterns

## Purpose

定义应急响应故障模式案例库（CASE 序列）的收录规则与沉淀位置，使每次排查沉淀的新故障模式都能按指纹被后续排查直接命中，且案例编号、条目要素和成因变体标注保持一致。

## ADDED Requirements

### Requirement: 案例库沉淀位置
新增故障模式、案例排查方法论与取证陷阱 SHALL 沉淀至 `references/emergency-response-patterns.md`。案例全文报告不进入本仓库，仅在案例条目中以报告文件名引用（如 `seek-report-template-action-deleted.md`）。

#### Scenario: 新故障模式入库
- **WHEN** 一次排查确认了既有案例库未覆盖的故障模式
- **THEN** 在 `references/emergency-response-patterns.md` 的「已知故障模式快速匹配」表中新增对应案例行
- **AND** 案例详情报告以文件名形式被引用，不复制全文进本仓库

### Requirement: 案例编号续接不重号
案例编号（CASE-NNN）SHALL 按现有序列末尾续接分配。分配前 MUST 检查现有最大编号，新编号不得与既有条目冲突或复用已废弃编号。

#### Scenario: 续接编号
- **WHEN** 现有案例库最大编号为 CASE-010，需要收录 3 个新故障模式
- **THEN** 新条目编号依次为 CASE-011、CASE-012、CASE-013

#### Scenario: 排查报告中的候选编号与实际可用编号冲突
- **WHEN** 源排查报告中自提的候选编号（如"CASE-009 候选"）已被既有库占用
- **THEN** 入库时顺延到可用编号，不沿用报告中的候选编号

### Requirement: 案例条目要素
每条案例条目 SHALL 包含故障指纹（可观测的现象/错误文案/状态组合）与核心结论（根因机制一句话）。以独立条目引用案例详情时，SHALL 至少提供指纹、根因、处置、检索入口四要素。

#### Scenario: 案例行可被指纹命中
- **WHEN** 排查者在日志或页面中观测到某案例记录的故障指纹（如 `Template action is deleted`、变更单"待发布"+设备"等待中"）
- **THEN** 在案例库中能按该指纹检索到对应案例行，并读到根因结论

### Requirement: 指纹匹配的成因变体标注
当新案例的现象指纹与既有案例相同但根因成因不同时，SHALL 以「成因变体」形式标注，MUST NOT 直接覆盖或静默合并到既有案例。

#### Scenario: 同指纹不同成因
- **WHEN** 新案例指纹与 CASE-004 相同（`当前环境对象不存在`），但成因为用户手动填错 `objectService` 而非定位脚本选错对象字段
- **THEN** 案例库记录两者指纹相同、成因不同，排查指引提示先区分成因再定归属

### Requirement: 既有案例的更正以追加方式进行
对既有案例结论的更正（如占用方定性变化）SHALL 以追加提示的方式体现在原条目上，MUST NOT 删除原有结论记录。

#### Scenario: CASE-003 占用方定性更正
- **WHEN** 排查证实流控令牌占用方可以是手动测试执行而非系统自动逃逸
- **THEN** CASE-003 条目追加"须确认令牌持有方发起方式"的提示，原"变更侧制造非终态"机制结论保留

### Requirement: 方法论与取证陷阱同步沉淀
案例入库时，其产生的可复用排查方法（归属判定、调用链闭环手段）与取证陷阱（检索漏检、停写数据源、误导文案）SHALL 沉淀至 `references/` 对应知识页：应急相关沉淀至 `references/emergency-response-patterns.md`，通用证据规则沉淀至 `references/evidence-and-boundaries.md`。

#### Scenario: 取证陷阱不重复沉淀
- **WHEN** 新案例的陷阱（如连字符 uuid 分词漏检）已被 `references/evidence-and-boundaries.md` 的通用规则覆盖
- **THEN** 不重复新增条目，仅在应急案例相关章节引用该通用规则
