"""seek-cli: 排查编排 CLI 工具

供 AI agent 调用的命令行工具，用于：
- 查询部署信息（集成 A1 CLI）
- 查询 SLS 日志（集成 aliyun-log SDK）
- 查询钉钉聊天（集成 dws CLI）
- 查询云网络工单（集成 qt-expert API）
- 查询数据库（集成 DMS MCP）
- 编排和约束排查链路
"""

__version__ = "0.10.2"

# 版本变更记录（最新在前）
CHANGELOG = {
    "0.10.2": [
        "fix: chain status/step/validate/context/report/usage 六命令统一会话异常映射 — 非法 session_id 返回 BAD_ARGUMENT(原冒泡误报 INTERNAL_ERROR)、损坏会话返回 CHAIN_CONFIG_ERROR 并保留路径级诊断(原被 except ValueError 吞成 NOT_FOUND)",
        "fix: 会话与模板路径安全加固 — session_id 强制 12 位小写 hex、reportTemplate 强制安全单文件名；get_session/_session_lock/_write_session_file 与 get_report_template 前置校验，拒绝路径型 id 与目录穿越",
        "fix: error_log context 落盘改为递归脱敏 — 敏感键归一化并匹配 *TOKEN/*SECRET 后缀，新增 depth(8)/nodes(1000)/bytes(64KB) 三重预算与 [truncated] 标记；None/int/float/bool 保持 JSON 原类型不漂移",
        "feat: seek init 新增 fully_ready 与 SLS verification_scope=doctor 字段 — fully_ready 只表示 init 自身负责的 A1/DMS 检查完成，SLS 资源活性继续由 seek doctor 验证，next_actions 不再重复提示",
        "fix: sls parse_time_range 区间格式收紧为恰好两个非空边界且 start<=end；query_by_config 改用 resolve_env 支持环境别名下的 queryDefaults 解析",
        "fix: DMS MCP 子进程 stderr 由 PIPE 改为 DEVNULL，消除 stderr 管道写满导致子进程阻塞、readline 30s 超时挂死的风险；a1/dws/dms subprocess 显式声明 shell=False(cmd 均为 list 形式，行为不变，仅防御性显式化)",
        "docs: 澄清 init --verify 的 fully_ready 语义与 error_log 上下文预算说明；安装路径 cd seek/cli→cd cli",
        "test: 补 chain 命令层非法/损坏 session id 错误码回归、路径型 id 拒绝、模板穿越拒绝、别名解析、fully_ready 与 context 预算用例(OpenSpec: harden-init-verification-error-context)",
    ],
    "0.10.1": [
        "fix: seek init 修正 A1 登录凭据探测路径 config.yaml→auth.yaml，已登录不再误报 needs_auth(OpenSpec: fix-init-a1-auth-detection)",
        "fix: seek init --verify 下 A1 configured 以 whoami 实测为准(成功 true/失败 false)，顶层 ready 恢复可信并对齐 DMS 行为",
        "test: 隔离 test_init_command 对宿主机 ~/.config/a1 的依赖，补默认不误报与 verify 覆盖文件探测回归",
    ],
    "0.10.0": [
        "feat: 新增 seek init，统一检查并引导配置 A1 CLI、DMS MCP 与 SLS 凭据",
        "feat: seek init --verify 支持 A1 登录态与 DMS MCP 工具发现验证",
        "docs: 接入引导关联 DMS MCP 与 A1 CLI 权威文档，并强调凭据安全",
    ],
    "0.9.0": [
        "feat: 通用故障链路新增异常/正常样本横向对比证据步骤",
        "feat: 根因报告区分直接报错点、首要触发根因与次生容错问题",
        "test: 增加数据源主因与代码放大场景的归因回归(OpenSpec: add-control-sample-root-cause-attribution)",
    ],
    "0.8.1": [
        "fix: 加固 Agent 场景 expected 类型校验并保持结构化错误输出",
        "fix: live runner 不再接收 replay 与 expected 评分标准",
        "fix: 新增准确的场景失败率和平均违规数指标，旧指标保留兼容标记(OpenSpec: fix-agent-evaluation-validation)",
    ],
    "0.8.0": [
        "feat: 新增协议、Agent 轨迹和最终报告三层场景评测",
        "feat: 支持 24 个脱敏场景 replay 与外部命令 live runner",
        "test: Agent 场景基线接入本地完整门禁(OpenSpec: add-agent-scenario-evaluation)",
    ],
    "0.7.0": [
        "feat: 链路步骤支持声明式 when 条件、自动 skipped 审计和 skipOutputs 默认输出",
        "feat: alert-ticket 在无相似工单时自动跳过 analyze-similar，减少无效调用",
        "fix: skipped 步骤可满足前置依赖且下游输入仍只能来自声明生产者(OpenSpec: add-conditional-chain-routing)",
    ],
    "0.6.0": [
        "feat: chain complete/amend 新增结构化 evidence，内置取证步骤缺失证据时拒绝推进",
        "feat: chain complete 支持可选 token usage，chain usage 按步骤和会话汇总且明确不参与评分",
        "test: Harness 增加 evidence 门禁与 token 统计黑盒回归(OpenSpec: add-chain-evidence-and-token-telemetry)",
    ],
    "0.5.1": [
        "fix: harness check 在 SEEK_HOME 不可写时仍返回 HARNESS_NOT_READY JSON，版本与错误日志降级提示写 stderr",
        "docs: 统一 parser/capabilities 中 SEEK_HOME 覆盖路径文案并补黑盒回归",
    ],
    "0.5.0": [
        "feat: 新增 seek harness check 离线就绪检查与仓库级 Harness 黑盒评测入口",
        "feat: 新增 SEEK_HOME，统一隔离 seek 配置、会话、日志、链路覆盖和版本状态",
        "fix: --help 不再写入版本标记；错误日志不可写时不覆盖原始命令结果；PR 检查改为临时 SEEK_HOME 下运行全量测试",
        "docs: 增加外部证据不可信与提示词注入防护契约，并强制 Skill/CLI 版本一致",
    ],
    "0.4.5": [
        "fix: 只读 SQL 校验补拦截锁定读 FOR SHARE/LOCK IN SHARE MODE(此前实测可绕过，与 0.3.1 声明不符)",
        "fix: chain 会话写入口(complete/amend/provide)改为锁内读-改-写全周期，并发操作同一会话不再丢更新",
        "fix: project add --sls-xxx 格式非法返回 BAD_ARGUMENT(原误报 INTERNAL_ERROR)",
        "fix: error_log context 落盘前脱敏(敏感键打码)并截断长值(2000 字符)",
        "refactor: 抽取 seek_cli/utils.py 收敛六处 file_lock 与四处原子写实现(锁路径与 0600 语义不变)",
        "refactor: 私有成员公共化(chain.PROBLEM_DESCRIPTION_INPUTS/expert.roar DEFAULT_HOST/sls SDK_AVAILABLE等，保留下划线别名)",
        "chore: 种子配置 14 个项目 repoPath 置空去除个人绝对路径(AGENT.md 已知待整改项)；.gitignore 补 .env*(OpenSpec: fix-cr-hardening-r1)",
    ],
    "0.4.4": [
        "feat: 新增 perf 命令组 — perf report 聚合分析耗时日志(命令/IO 分组 count/p50/p95/max、ioSharePct 归因占比、--session/--keyword 过滤、优化方向 hint)，perf clear 原子清空(OpenSpec: add-perf-report-clear)",
    ],
    "0.4.3": [
        "feat: 新增 perf 耗时观测 — 命令级与集成 IO 级耗时写入 ~/.seek/logs/perf.jsonl(span: command/sls_query/a1_subprocess/dms_call)，options.perf_log 开关(默认开)，SEEK_SESSION_ID 环境变量关联会话步骤，写失败静默不影响命令(OpenSpec: add-perf-telemetry，含 09-03 CR 修复)",
    ],
    "0.4.2": [
        "fix: notification 链路 step4 移除指向 notice-service 的项目级 SLS 死路提示 — 该项目 environments 为空，实测必然 SLS_QUERY_ERROR(environment not configured)；改为 sls query 直查模式(--endpoint/--sls-project/--logstore)与 deploy changes(走 a1AppName)",
        "fix: notification step4 agentInstructions 补 notice_service_evidence 的四条合法取证来源(直查/DB/本地源码/部署侧)，并规定四条都拿不到时必须写明验证边界，不得留空或推测",
        "fix: 删除种子项目配置中从未生效的顶层 queryAliases(error/warn/slow/timeout) — 代码与命令输出零引用，留着会被误认为可用的查询快捷方式",
        "test: test_doc_consistency 新增 ChainToolHintResolutionTest — 链路 tools 里点名走项目级 sls 查询的项目，必须在种子配置中有 enabled 的 SLS platform",
    ],
    "0.4.1": [
        "feat: 新增 chain report — 对 completed 会话生成带产出日期前缀的报告文件名与已渲染模板头部(slug kebab-case 校验/防双重前缀，CLI 不落盘)",
    ],
    "0.4.0": [
        "feat: sls query 关键词查询返空时自动探测 GetIndex 索引形态，无全文索引或分词不匹配均输出 warnings/indexCheck，防'静默返 0'误判",
        "feat: doctor 新增 --liveness-window(如 30d) 活性检查，窗口内 0 条日志的 logstore 标记 stale",
        "feat: sls query 新增 --query-file(支持 - stdin)，--time 支持 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS' 人类可读时间窗",
        "feat: deploy env 环境同义词自动扩展(生产→正式/prod/online...)，未命中时 hint 列出全部 pipeline 名",
        "feat: deploy branch 补齐各 pipeline 最近实例的真实部署分支(releaseBranch)与 commit，不再只返回应用元信息",
        "feat: stability-monitor 纳入内置 SLS 配置(pre/prod，qt-monitor-cn-shanghai，indexHint 标注分词不匹配需 SQL like 全扫描)",
        "feat: 新增 cron-task-health 内置链路(定时任务健康巡检 5 步)，default 链路 query-logs 时间窗按问题描述确定",
        "docs: evidence-and-boundaries 补'静默返 0'识别(无索引/分词不匹配)与'文档 logstore ≠ 活 logstore'经验；补 stability-monitor call-chain 文档",
    ],
    "0.3.5": [
        "fix: 项目用户配置改为补丁合并，保留内置项目的 A1/SLS 字段并明确损坏配置错误",
        "fix: SLS logs 校验 --max，多 logstore 返回逐源截断信息",
        "fix: A1 环境别名匹配、chain 约束/完成态与 capabilities/global format 一致性",
    ],
    "0.3.4": [
        "feat: notification 链路改为事件定位→上游拦截五件套→分叉验证，先判断通知是否生成",
        "docs: 新增告警未推送清单、两套静默体系、SLS/DB 取证避坑与通知知识卡片",
    ],
    "0.3.3": [
        "新增 config 命令组 — 统一配置管理(~/.seek/config/seek.json): show/get/set/unset/path",
        "配置读取链统一: 环境变量 > seek.json > 旧文件(credentials.json/expert.json/roar.json/trace.json,兼容) > 默认值",
        "options.quiet_warnings 可替代 SEEK_QUIET_WARNINGS=1 抑制安全警告",
        "doctor 无凭据时提示 seek config set 配置路径; capabilities 登记 config 命令组",
    ],
    "0.3.2": [
        "docs: 报告模板新增可复用排查路径、证据点、分支决策、结论映射与验证边界",
        "docs: alert-ticket 报告指引要求产出可直接沉淀到云网络工单的排查逻辑",
    ],
    "0.3.1": [
        "fix: db query 限制为只读 SELECT/WITH/EXPLAIN，拒绝写入、多语句和锁定查询",
        "fix: chain complete 校验 outputs 对象、声明字段完整性和 requiredInputs 生产步骤来源",
        "fix: chain 首步 requiredInputs 不再默认豁免，alert-ticket 必须注入 flow_id",
        "fix: doctor live 检查被跳过时返回验证未完成，不再误报通过",
        "fix: project 配置写入使用文件锁与原子替换，避免并发丢失或中断损坏",
    ],
    "0.3.0": [
        "新增 notify 命令组 — 通知触达查询(roar noti-query)，deliveryState/运营商回执码自动中文解读，注意仅近7天",
        "新增 doctor 命令 — 配置体检(SLS 结构校验+SDK 实测存在性)",
        "新增 chain amend — completed 后回填更正(追加correction不覆盖)",
        "新增 chain start --context — 初始上下文注入(如 flow_id)",
        "fix: sls logs/query unhashable type: 'dict' 必现 bug，改为多 logstore 跨 region 合并查询",
        "fix: chain status 输出结构恒定(completed 时 current_step_detail=null)",
        "fix: db 连接失败附 fallback 指引; sls config 返回全部条目",
        "docs: SKILL v0.3 跨region铁律/外部依赖取证/根因模式库/更正记录",
    ],
    "0.2.0": [
        "新增 db 命令组 — DMS MCP 集成(数据库查询)",
        "新增 skill 命令组 — 安装/更新/状态/卸载",
        "新增 errors 命令组 — 错误日志自动记录和查看",
        "新增 alert-ticket 排查链路(8步) — 工单排查+人员定位+报告模板",
        "SKILL v0.2 强制链路排查约束(参考 ae-sdd 门禁模式)",
        "SKILL v0.2.1 改为仅 /seek 显式调用",
        "CLI 错误日志自动记录到 ~/.seek/logs/errors.jsonl",
        # code-review 修复集（commit fix/code-review-findings-r2）
        "fix: 修复 22 个 code review findings（sys.exit 错误日志丢失、a1 deploy orders 丢 app_name、dms readline 永久挂死、HTTP 明文传输警告、seed 配置硬编码路径等）",
        "fix: 修复 patch-level review 9 个新引入 bug（NF-01 sys.exit 控制流分离、NF-02 dms proc 残留自检、NF-03 SLS 凭据缓存失效接口、类型守卫等）",
        "chore: SKILL.md 补充 skill update / version 命令速查",
        "refactor: trace._resolve_topology_file 下沉到 config.get_topology_file()（commands 层不再读配置文件）",
        "docs: 新增 AGENT.md — Git 分支规范与开发约束",
        "feat: skill update 输出源码版本/commit/mtime，便于判断本地源码是否最新",
        "docs: SKILL.md 补充 skill update 输出格式示例",
        "fix: chain.validate_step 检查 requiredInputs 时穿透命名空间（之前只查顶层导致所有 step>1 永远 invalid）",
        "docs: SKILL.md 新增 Pitfalls/工单证据章节（PATH/validate/dws 下载等 5 条实战经验）",
        "docs: SKILL.md 补充默认链路 environment 字段缺失 workaround + dws download-media 截图取证 fallback（未亲测，标注）",
        "fix(NF-10): error_log.py 的 from collections import deque 从函数体上移到模块顶部（PEP 8 E402）",
        "fix(NF-11): get_topology_file() 配置失效时 stderr 警告，避免静默回退",
        "docs: SKILL.md 宽时间窗验证证据从占位符 N 改为具体数字（2 条）",
        "docs: SKILL.md frontmatter version 拆分为 skill_doc_version + cli_version_ref 区分文件版本和 CLI 版本",
    ],
    "0.1.0": [
        "初始版本",
        "project/deploy/sls/trace/chain/dingtalk/ticket 8 个命令组",
        "3 条排查链路: default/alert-enrichment/notification",
        "capabilities 能力发现命令",
        "集成: A1 CLI / aliyun-log SDK / dws CLI / qt-expert API",
    ],
}
