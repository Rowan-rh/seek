# seek CLI 常见错误排查指南

记录 CLI 各命令组常见报错及修复方式。

---

## 1. 安装与启动

### 1.1 `neither 'setup.py' nor 'pyproject.toml' found`

**场景**: `pip3 install -e .` 报错

**原因**: 在 `seek/` 根目录执行了安装命令，但 `setup.py` 在 `cli/` 子目录

**修复**:
```bash
cd /path/to/seek/cli
pip3 install -e .
```

### 1.2 `command not found: seek`

**场景**: 终端直接输入 `seek` 无响应

**原因**: `seek` 脚本安装在 `~/Library/Python/3.9/bin/`，不在 PATH

**修复**:
```bash
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

或用 `python3 -m seek_cli` 替代。

### 1.3 `urllib3 v2 only supports OpenSSL 1.1.1+`

**场景**: 每次命令输出前出现 urllib3 警告

**原因**: macOS 自带的 LibreSSL 2.8.3 与 urllib3 v2 不兼容，无害

**修复**: 已在 `cli.py` 中通过 `warnings.filterwarnings` 抑制，无需处理

### 1.4 `seek init` 显示接入未就绪

**场景**: 首次使用、换机器或凭据轮换后，需要确认排查能力是否可用

**检查**:
```bash
seek init             # 本地安装/配置检查，不访问外部服务
seek init --verify    # 验证 A1 登录态和 DMS MCP 工具发现
```

按返回的 `next_actions` 处理：

- A1 CLI：参考 <https://a1.io.alibaba-inc.com/docs/guide/>，安装后执行 `a1 auth login`。
- DMS MCP：参考 <https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y>，配置 `~/.qoderwork/mcp.json` 后执行 `seek db tools`。
- SLS：成对配置 `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`，或使用 `seek config set sls.access_key_id ...` 与 `sls.access_key_secret ...`；再运行 `seek doctor --liveness-window 24h`。

不要把真实 AK/SK、Token 或带密钥的 MCP URL 粘贴到工单、对话、日志或代码仓库。

---

## 2. deploy — A1 CLI 集成

### 2.1 `a1 CLI not found`

**场景**: `seek deploy branch <project>` 报错

**原因**: A1 CLI 未安装或不在 PATH

**检查**:
```bash
which a1  # 应输出一个可执行文件的绝对路径
```

**修复**:
```bash
export PATH="$HOME/.local/bin:$PATH"
# 或安装 A1 CLI，参考 https://a1.io.alibaba-inc.com/docs/guide/
```

### 2.2 `application not found: qt-monitor-ops`

**场景**: `seek deploy branch qt-monitor-ops` 报 A1 找不到应用

**原因**: Aone 平台应用名和项目目录名不一致

**修复**: 检查项目配置中的 `a1AppName` 字段是否正确（优先看用户级 `~/.seek/config/projects.json`，其次运行时权威 `cli/seek_cli/resources/config/projects.json`；改 `cli/config/projects.json` 这个人类编辑镜像不会生效，且两份副本须同步）：

| 项目目录名 | Aone 应用名 |
|---|---|
| qt-monitor-ops | qt-monitor-data |
| notice-service | qt-notice-service |
| 其余 8 个 | 与目录名一致 |

用 `seek project show <name>` 确认 `a1AppName` 值。

### 2.3 `a1 auth login` 未执行

**场景**: A1 命令返回认证错误

**修复**:
```bash
a1 auth login
```

---

## 3. sls — SLS 日志查询

### 3.1 `No SLS credentials found`

**场景**: `seek sls logs/query` 报认证错误

**原因**: 找不到阿里云 AK/SK

**检查顺序**:
1. 环境变量：`ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
2. `${SEEK_HOME:-~/.seek}/config/seek.json` 中的 `sls.access_key_id` / `sls.access_key_secret`
3. `${SEEK_HOME:-~/.seek}/credentials.json`（旧格式，继续兼容）
4. `~/.aliyun/config.json` 或 `~/.alibabacloud/config.json`（阿里云 CLI 配置）

**修复**:
```bash
# 方式1（推荐）: 通过环境变量注入，避免把密钥写入命令历史
export ALIBABA_CLOUD_ACCESS_KEY_ID='<AK>'
export ALIBABA_CLOUD_ACCESS_KEY_SECRET='<SK>'

# 方式2: 写入 seek 统一配置
seek config set sls.access_key_id '<AK>'
seek config set sls.access_key_secret '<SK>'

# 配置后验证具体 SLS project/logstore
seek doctor --liveness-window 24h
```

> 不要将真实 AK/SK 粘贴到对话、工单、日志或代码仓库；优先使用最小只读权限凭据。

### 3.2 `environment 'xxx' not configured for project`

**场景**: `seek sls logs <project> --env xxx` 报环境未配置

**原因**: `projects.json` 中该项目没有该环境的 SLS 配置

**修复**:
```bash
# 查看项目支持的环境
seek sls config <project>

# 添加缺失的环境
seek project add <project> --sls-xxx endpoint/project/logstore
```

### 3.3 `invalid time_range 'xxx'`

**场景**: `--time` 参数格式错误

**正确格式**:
- `15m` / `1h` / `2d` — 最近 N 分钟/小时/天
- `1785738662,1785742262` — unix 时间戳范围（逗号分隔）

### 3.4 SLS 查询返回 0 条

**排查**:
1. 确认 `--env` 正确（daily/pre/prod 对应不同 logstore）
2. 确认 `--time` 覆盖了目标时间段
3. 确认项目 SLS 配置中的 `logstore` 名称正确
4. 尝试 `--query "*"` 确认 logstore 有数据

---

## 4. db — 数据库查询（DMS / 本地直连双 backend）

> §4.1~§4.4 是 DMS 路径（生产/受管实例，`database_id` 寻址）；§4.5~§4.8 是本地直连路径（日常/预发，`--conn` 或 `--project`+`--env` 寻址）。

### 4.1 `mcp.json not found at ~/.qoderwork/mcp.json`

**场景**: `seek db` 命令报错

**原因**: DMS MCP Server 未配置

**修复**: 在 `~/.qoderwork/mcp.json` 中添加:
```json
{
  "mcpServers": {
    "dms-mcp-server": {
      "command": "uvx",
      "args": ["alibabacloud-dms-mcp-server-inner@latest"],
      "env": {
        "ACCESS_KEY_ID": "<your_ak>",
        "ACCESS_KEY_SECRET": "<your_sk>"
      }
    }
  }
}
```

参考: [集团版 DMS MCP 使用指南](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y)

### 4.2 `DMS MCP server closed connection` / 首次调用超时

**原因**: `uvx` 首次运行需要下载安装包，耗时较长

**修复**: 等待 30-60 秒后重试。后续调用会使用缓存，速度正常。

### 4.3 `Field required [type=missing, input_value={'schemaName': '...'}]`

**场景**: DMS 工具参数校验失败

**原因**: DMS MCP 参数使用 **snake_case**，不是 camelCase

**正确参数名**:

| 工具 | 参数 |
|------|------|
| searchDatabase | `schema_name` |
| listTables | `database_id` |
| getTableDetailInfo | `database_id`, `table_name` |
| executeScript | `database_id`, `script` |

### 4.4 `uvx not found`

**原因**: 未安装 uv 包管理器

**修复**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4.5 `PyMySQL 未安装。安装方式: pip install seek-cli[mysql] 或 pip install pymysql`

**场景**: `seek db query/tables/schema` 走本地直连（`--conn` 或 `--project`+`--env`）时报 `DB_ERROR`

**原因**: 本地直连 backend 依赖 PyMySQL，属可选依赖，默认安装不含

**修复**:
```bash
pip3 install 'seek-cli[mysql]'    # 或 pip3 install pymysql
```

### 4.6 `密码环境变量 'VAR' 未设置（profile 使用 env:VAR 引用）`

**场景**: `seek db query --conn <name>` 报 `DB_STORE_ERROR`

**原因**: profile 的 `password` 用 `env:VAR` 前缀引用环境变量（避免明文落盘），但当前 shell 未导出该变量

**修复**:
```bash
export VAR='真实密码'        # 写进 ~/.zshrc 或 direnv，不要写回 db.json
seek db conn test <name>     # 复验连通性
```

### 4.7 `连接 profile 'xxx' 不存在（现有: ...）` / `无 profile 绑定到 project=... env=...`

**场景**: `--conn` 名称写错，或用 `--project`+`--env` 反查时无 profile 绑定到该组合（`DB_STORE_ERROR`）

**原因**: profile 未创建，或创建时未带 `--project`/`--env` 绑定。反查命中**多个** profile 时也会报错，并要求用 `--conn` 显式指定

**修复**:
```bash
seek db conn list            # 查看现有 profile 与其 bind
seek db conn add <name> --type mysql --host H --port 3306 --database D \
  --user U --password 'env:VAR' --project <project> --env daily
seek db conn test <name>
```

配置文件在 `~/.seek/config/db.json`；`--conn` 与位置参数 `database`（DMS）互斥，`--project` 模式必须同时给 `--env`。

### 4.8 `profile 'xxx' 绑定生产类环境 (prod)，本地直连默认拒绝`

**错误码**: `PROD_DIRECT_CONNECT_FORBIDDEN`

**原因**: 生产熔断——`bind.env` 为 `prod`/`online`/`publish*` 时本地直连默认拒绝

**修复**: 生产优先走 DMS：`seek db query <database_id> --sql "..."`。确需本地直连才加 `--i-know-this-is-prod`。

**相关约束**: 两条 backend 均只允许**单条只读 SQL**，违规返回 `READ_ONLY_SQL_REQUIRED`，原因可能是「仅允许 SELECT、WITH 或 EXPLAIN 只读查询」「只读查询中不允许写入、DDL、事务控制、文件导出或 FOR UPDATE」「只允许单条 SQL 查询，不支持多语句」「不允许使用可执行 SQL 注释」或「SQL 不能为空」。本地直连结果默认 500 行截断（`--max` 上限 5000），取证时看输出的 `backend` 与 `truncated` 字段。

---

## 5. dingtalk — dws CLI 集成

### 5.1 `dws CLI not found`

**场景**: `seek dingtalk` 命令报错

**原因**: dws CLI 不在 PATH

**检查**:
```bash
ls ~/.qoderwork/bin/dws
```

**修复**: dws CLI 是 QoderWork 内置工具，确保 QoderWork 已安装。代码中已硬编码 `~/.qoderwork/bin/dws` 路径作为 fallback。

### 5.2 `[AUTH_PERMISSION_DENIED] Permission denied`

**场景**: 拉取群聊消息返回权限拒绝

**原因**: 当前用户不在目标群内

**修复**: 确认用户已加入目标群，或换一个用户已加入的群测试。

### 5.3 `unknown subcommand "list-unread" for "dws chat message"`

**场景**: 子命令名不对

**原因**: dws CLI 子命令名称可能随版本变化

**修复**: 查看可用子命令:
```bash
~/.qoderwork/bin/dws chat message --help
```

### 5.4 `'list' object has no attribute 'get'` / 消息列表为空

**原因**: dws 不同命令返回的 JSON 结构不统一（`result` 有时是 dict 有时是 list）

**已修复**: `commands/dingtalk.py` 中有 `_extract_result()` 函数兼容两种结构。若仍遇到此问题，检查 dws 原始输出:
```bash
~/.qoderwork/bin/dws <command> --format json | python3 -m json.tool
```

---

## 6. ticket — qt-expert API 集成

### 6.1 `API /xyt/xxx returned HTTP 5xx` / 连接超时

**原因**: qt-expert 预发环境不可达或服务异常

**检查**:
```bash
curl -s "http://pre-qt-expert.aliyun-inc.com/xyt/queryDiagnoseFlow?flowType=afterSale&pageSize=1&pageNum=1" | head -20
```

**修复**: 等待服务恢复，或切换环境:
```bash
export QT_EXPERT_HOST="http://qt-expert.aliyun-inc.com"  # 生产
```

### 6.2 `API error: code=1, msg=...`

**原因**: qt-expert 业务级错误，通常是参数缺失或权限不足

**排查**: 检查请求参数:
- `ticket detail` 需要 `flowId`（FLOW-xxx 格式）
- `ticket history` 需要 `questionTitle`（标题关键词）
- `ticket detail` 的 `--user-id` 和 `--dept` 用于权限校验，不传可能看不到全部字段

### 6.3 `queryHistoryDiagFlow` 返回数据解析失败

**原因**: 该接口返回的 `data` 字段是 JSON 字符串（不是 JSON 对象），且结构可能是 list 或 dict

**已修复**: `expert_client.py` 的 `_call_api()` 自动二次解析 JSON 字符串。`commands/ticket.py` 兼容 list/dict 两种结构。

---

## 7. chain — 排查链路引擎

### 7.1 `chain 'xxx' not found`

**场景**: `seek chain start xxx` 报错

**原因**: 链路名不存在

**检查**:
```bash
seek chain list  # 查看可用链路
```

链路清单以 `seek chain list` 输出为权威，本文不枚举链路名与条数（会随定义漂移）。机器定义在 `cli/seek_cli/resources/chains/default.json`（运行时权威，代码只读这份），`cli/chains/default.json` 是人类编辑镜像，两者须保持一致。链路选择规则与作业流程见 [`../references/SOP-seek-investigation.md`](../references/SOP-seek-investigation.md)。

**错误码区分**: `chain show`/`chain status`/`chain context`/`chain report` 对不存在的链路或会话返回 `NOT_FOUND`；`chain start` 链路名错时返回 `CHAIN_NOT_FOUND`。

### 7.2 `step N requires step M to be completed first`

**场景**: `seek chain validate <session> --step N` 返回 invalid

**原因**: 链路约束 — 必须先完成前置步骤

**修复**: 按顺序执行，先 `chain complete` 前一步:
```bash
seek chain step <session>     # 查看当前步骤
seek chain complete <session> --summary "..." --outputs '{...}'  # 完成当前步骤
```

### 7.3 `session 'xxx' not found`

**场景**: 会话 ID 不存在

**原因**: 会话已删除，或 session_id 输错

**检查**:
```bash
seek chain sessions  # 列出最近会话
```

会话文件存储在 `~/.seek/sessions/<session_id>.json`。

---

## 8. notify — 通知触达查询

### 8.1 `ROAR_API_ERROR`

**场景**: `seek notify query <queryId>` 报错

**原因**: roar noti-query 接口异常，或 queryId 非法

**检查**:
```bash
seek config get hosts.roar     # 确认 roar 域名配置
```

- `queryId` 必须是从日志/响应中提取的**下游任务 ID**（形如 `ali-ivr-<uuid>`），不是告警 uuid
- 上游是否生成通知请求属另一条排查路径，见 [`../references/investigation-patterns.md`](../references/investigation-patterns.md)

### 8.2 查询返回空记录

**原因**: 多数情况是超出留存期，不是平台未投递

**处置**: **仅支持近 7 天数据**。先确认 queryId、事件时间与查询窗口都在保留期内；都在保留期且仍无记录，才可判定平台侧未实际投递，并在报告中标注留存边界。状态码解读以返回的 `deliveryStateDesc` 为准，不要凭记忆解释数字。

---

## 9. config / doctor / skill — 配置、体检与 Skill 管理

### 9.1 `BAD_CONFIG_KEY`

**场景**: `seek config get/set/unset <key>` 报错

**原因**: key 不在可管理项白名单内

**可管理项**: `sls.access_key_id`、`sls.access_key_secret`、`sls.security_token`、`hosts.expert`、`hosts.roar`、`trace.topologyFile`、`options.quiet_warnings`

**检查**:
```bash
seek config show     # 全部配置项的生效值与来源（secret 脱敏）
seek config path     # 配置目录与各文件存在状态
```

### 9.2 `DOCTOR_ISSUES` / `DOCTOR_INCOMPLETE`

**场景**: `seek doctor` 返回非零退出码

**原因**: `DOCTOR_ISSUES` = 检出配置问题（结构缺失、project/logstore 实测不存在或已停写）；`DOCTOR_INCOMPLETE` = 部分检查未能完成（凭证缺失或 SLS API 不可达）

**处置**: 按 `data` 里的条目逐项修。`not_found` 说明配置是幻影，`stale` 说明 logstore 已停写，两者都会造成 SLS「静默返 0」误判。只想校验结构不调 API 用 `--no-live`。

### 9.3 `invalid --liveness-window` / `--liveness-window requires live checks`

**错误码**: `BAD_ARGUMENT`

**原因**: 窗口格式非法（应形如 `30d`），或同时传了 `--no-live`——活性检查必须实调 SLS API

**修复**:
```bash
seek doctor --liveness-window 30d      # 去掉 --no-live
```

### 9.4 skill 安装/更新状态异常

**场景**: `seek skill install` / `update` / `status` 结果与预期不符

**检查**:
```bash
seek skill status    # 安装状态、是否符号链接、源码版本
```

`skill update` 输出含 `skill_doc_version`、`cli_version`、`source_commit`、`source_skill_mtime`；比对 `source_commit` 与源码仓库 `git rev-parse --short HEAD` 判断本地源码是否最新。普通目录会先压缩为同级 `.tar.gz` 备份，再迁移为符号链接。

---

## 10. 通用问题

### 10.1 `unexpected error: ...` (INTERNAL_ERROR)

**排查**: 查看原始错误:
```bash
python3 -m seek_cli <command> 2>&1  # 不过滤 stderr
```

常见原因:
- Python 依赖缺失 → `pip3 install -e .` 重新安装
- JSON 文件格式错误 → 用 `python3 -m json.tool < file.json` 验证
- 路径权限问题 → 检查 `~/.seek/` 目录可写

### 10.2 输出中文乱码

**原因**: 终端编码不是 UTF-8

**修复**:
```bash
export LANG=en_US.UTF-8
export PYTHONIOENCODING=utf-8
```

### 10.3 capabilities 命令输出不包含新命令

**原因**: `capabilities.py` 是手动维护的，新增命令后需同步更新

**修复**: 编辑 `cli/seek_cli/commands/capabilities.py`，在 `commands` dict 中添加新命令组。

---

## 快速诊断清单

```bash
# 1. CLI 是否正常
seek capabilities

# 2. 项目配置是否正确
seek project list

# 3. A1 CLI 是否可用
seek deploy branch qt-monitor-ops

# 4. SLS 是否可用
seek sls config qt-monitor-ops --env daily

# 5. DMS MCP 是否可用
seek db tools

# 6. dws CLI 是否可用
seek dingtalk unread

# 7. qt-expert API 是否可用
seek ticket search --keyword "test" --page-size 1

# 8. 链路引擎是否正常
seek chain list
```
