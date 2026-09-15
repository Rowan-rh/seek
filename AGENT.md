# agent.md — seek CLI 开发规范与约束

> 本文件为 AI Agent 和开发者提供开发行为约束，所有代码变更必须遵守以下规则。

---

## 1. Git 分支规范（🔴 强制）

### 1.1 主分支与长期分支

- **`main` 是远程受保护分支，仅承担对外发布**，**禁止任何开发者直接 `push` 到 `main`，也不允许在本地直接 `commit`/`merge` 后再强推**。所有变更必须以 PR/MR 方式通过评审后才能在远程合入。
- **`develop` 是集成分支**，开发者把完成评审的工作分支合并到这里，再由维护者从 `develop` 提 PR 到 `main`。
- **`main`/`develop` 都是不允许直接 `push` 的远程保护分支**；本地只允许切出工作分支，或在本地通过 PR review flow 准备好改动后推送。

### 1.2 工作分支前缀

不同目的的开发工作必须在对应的分支目录下创建新分支，前缀规定如下：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/` | 新功能开发 | `feat/add-db-query-cache` |
| `fix/` | Bug 修复 | `fix/deploy-orders-missing-app` |
| `refactor/` | 代码重构（不改变外部行为） | `refactor/extract-sls-config` |
| `chore/` | 工程化/依赖/构建 | `chore/update-aliyun-sdk` |
| `docs/` | 文档变更 | `docs/add-contributing-guide` |
| `test/` | 测试相关 | `test/add-chain-coverage` |
| `ci/` | CI/CD 相关 | `ci/add-lint-pr-check` |

**命名规则：**
- 前缀后跟短横线分隔的小写英文描述
- 总长度不超过 80 字符
- 示例：`fix/error-log-sys-exit-blocking` ✅ 、 `fix_bug` ❌

### 1.3 分支创建与合并流程

开发 → 评审 → 合入 `develop` → 维护者从 `develop` 推 `main`：

```text
1. git fetch origin
2. git checkout -b <prefix>/<description> origin/develop
3. 开发 + 提交
4. git push -u origin <prefix>/<description>
5. 创建 PR 到 develop（项目默认 base 分支）
6. 通过 Code Review 后合并到 develop
7. 维护者从 develop 创建/更新 PR 到 main，准备发布
```

**禁止项：**
- 直接 `git push` 到 `main` 或 `develop` —— 都会被远程保护分支拒绝；
- 在 `main` 上直接 `git commit`、`git merge` 后再强推 —— 远程分支是 SSOT，强行改写会与团队协作者冲突；
- 未经评审合并任何分支到 `develop`/`main`。

**提交信息规则：**
- 提交标题使用中文，采用 `<类型>: <简明说明>` 格式，例如：`fix: 修复部署单缺少应用名`、`docs: 增加贡献指南`。
- 标题不超过 80 个字符；必要的技术标识、代码符号和产品名可保留英文。
- 一次提交只表达一个可独立审查的变更意图。


| 操作 | 允许 | 说明 |
|------|------|------|
| 在工作分支上 `git commit` | ✅ 允许 | 工作分支可自由提交 |
| 在工作分支上 `git push` | ✅ 允许 | 推送远程工作分支 |
| 直接 `git push` 到 `develop`/`main` | ❌ 禁止 | 远程保护分支，必须走 PR |
| 本地在 `main` 上直接 `commit`/`merge` 后强推 | ❌ 禁止 | 会与远程 SSOT 冲突并丢失评审记录 |
| `git push --force` 到 `develop`/`main` | ❌ 严格禁止 | |
| 直接 `git merge` 到 `main` | ❌ 禁止 | 必须通过 PR/MR |
| 将功能分支 `merge` 到 `main`（PR 方式） | ✅ 允许 | Review 通过后方可合入 |
| `git push --force` 到 `main` | ❌ 禁止 | 严格禁止 force push |
| 在 `main` 上直接 `git commit` | ❌ 禁止 | 任何修改必须走分支流程 |

---

## 2. 代码规范

### 2.1 Python 编码风格

- **Python 版本:** >= 3.8
- **命名风格:** 遵循 PEP 8
  - 函数/变量: `snake_case`
  - 类: `PascalCase`
  - 模块级常量: `UPPER_SNAKE_CASE`
- **类型注解:** 公开函数必须加类型注解（`typing` 模块）
- **文档字符串:** 每个公开函数使用 Google 风格 docstring（参见现有代码 `chain.py`、`config.py`）

### 2.2 模块职责

| 模块 | 职责 | 禁止 |
|------|------|------|
| `cli.py` | CLI 入口、参数解析、路由 | 不可包含业务逻辑 |
| `commands/*.py` | 命令处理函数，调用 integrations | 不可直接操作文件 I/O |
| `integrations/*.py` | 外部系统集成封装 | 不可依赖 argparse |
| `config.py` | 配置加载/保存 | 不可混入命令逻辑 |
| `output.py` | 结果格式化/输出 | 不可直接调用 `sys.exit()` |
| `chain.py` | 排查链路引擎 | 不可依赖外部服务 |
| `error_log.py` | 错误日志读写 | 不可输出到 stdout |

### 2.3 错误处理

- 所有 `open()` 必须指定 `encoding="utf-8"`
- 读取配置文件必须包裹 `try/except json.JSONDecodeError` 返回友好错误
- 禁止裸 `except:` 或无具体异常类型的 catch
- 禁止在 `output.py` 中调用 `sys.exit()`，退出逻辑统一在 `cli.py:main()` 中

### 2.4 安全

- 所有 subprocess 调用使用 `list` 形式传参（非 shell 字符串），`shell=False`
- 敏感参数（AK/SK/Token/Password）不可打印或记录完整值
- 配置文件中的凭据使用 `error_log.py` 脱敏逻辑

---

## 3. 项目资产维护

### 3.1 `capabilities.py` 同步

每次新增/删除/修改命令或参数时，**必须同步更新** `commands/capabilities.py` 中的命令描述：
- 新增子命令 → 在对应 section 添加描述
- 修改参数 → 更新 args 列表
- 注意 `version` 字段应与 `__init__.py` 中的 `__version__` 一致（使用 `from seek_cli import __version__` 而非硬编码）

### 3.2 文档与知识加载

- 命令接口变更时，更新 `commands/capabilities.py`；`seek capabilities` 是参数和响应 schema 的实时权威来源。
- `SKILL.md` 只维护显式触发规则、最小工作流、不可绕过约束、链路选择和按需加载索引；不要把案例、长命令手册或场景经验堆入入口。
- 具体知识按职责维护：命令示例在 `references/command-reference.md`，证据标准在 `references/evidence-and-boundaries.md`，场景模式在 `references/investigation-patterns.md`，人可执行的排查作业流程在 `references/SOP-seek-investigation.md`，CLI 故障按症状维护在 `cli/TROUBLESHOOTING.md`。
- 机器执行所需的 `requiredInputs`、`outputs`、`constraints` 和关键结论边界必须保留在链路定义 `default.json`；展开说明和案例可以进入 reference。
- **链路定义与种子项目配置各有两份副本，必须保持一致**：`cli/chains/`、`cli/config/` 是人类编辑镜像，`cli/seek_cli/resources/chains/`、`cli/seek_cli/resources/config/` 是运行时权威（`chain.py`/`config.py` 只读后者，`setup.py` 只打包后者）。只改镜像不会生效。镜像一致性由 `cli/tests/test_doc_consistency.py`（`default.json`、`projects.json`）与 `cli/tests/test_report_templates.py`（报告模板）守护。
- 文档不得写死会随代码漂移的数量（链路条数、项目数、命令组/子命令数），一律指向 `seek chain list`、`seek project list`、`seek capabilities`；`cli/tests/test_doc_consistency.py` 会拦截这类硬编码计数。
- 新增可复用知识至少标注：适用症状、前置输入、证据来源、分支判断、结论边界、验证时间或 CLI 版本。未经验证的流程必须显式标记为待验证。

### 3.3 仓库临时工作区（🔴 强制）

- Agent、代码审查、调试和开发辅助流程产生的临时报告、日志、截图、中间数据，必须通过 `python3 scripts/seek_tmp.py create --slug <task-slug>` 创建独立工作区。
- 固定布局为 `.seek-tmp/runs/YYYY-MM-DD/<HHMMSSZ-slug-shortid>/`，运行目录内只使用 `inputs/`、`work/`、`outputs/`、`logs/` 和 `manifest.json`；禁止直接向 `.seek-tmp/` 根目录平铺任务文件。
- `inputs/` 仅放本次任务所需的复制件或脱敏快照，`work/` 放可丢弃中间结果，`outputs/` 放待审阅或待迁出的结果，`logs/` 放执行与诊断日志。
- 正式源码、OpenSpec 文档和需要提交/交付的报告必须移入其约定目录，不得长期保存在 `.seek-tmp/`；清理时以完整运行目录为单位。
- `.seek-tmp` 不替代 `${SEEK_HOME:-~/.seek}`、操作系统临时目录或原子写临时文件。`utils.py` 的 `.filename-*.tmp` 必须继续与目标文件同目录，以保持 `os.replace()` 的同文件系统原子语义。
- 临时工作区不得保存未脱敏凭据、Token、Cookie 或生产数据原文。

### 3.4 版本号管理

- `__version__` 定义在 `seek_cli/__init__.py`
- `CHANGELOG` 定义在 `seek_cli/__init__.py`
- 每次功能变更在 CHANGELOG 中添加条目
- **正式发布前，所有对外发布版本必须保持 `<1.0.0`**，包括 CLI `__version__`、`SKILL.md#skill_doc_version` 和 `SKILL.md#cli_version_ref`。
- `0.9.x` 之后的功能版本使用 `0.10.0`、`0.11.0` 等合法 SemVer，禁止因十进制直觉直接升级为 `1.0.0`。
- 升级到 `1.0.0` 必须由用户或维护者明确批准，并同步更新 CHANGELOG、SKILL.md 和相关版本文档。
- `schema_version`、链路/项目配置内的格式版本属于独立的数据契约版本，不因本条发布版本约束自动降级或改号。

---

## 4. 禁止事项

| 禁止 | 原因 |
|------|------|
| 在种子配置文件（`cli/config/projects.json` 与运行时权威 `cli/seek_cli/resources/config/projects.json`）中存储本地绝对路径 | 影响其他机器可移植性；`resources/` 下的副本会随包分发。种子 `repoPath` 已统一置空（fix-cr-hardening-r1），自定义仓库路径写入用户级 `~/.seek/config/projects.json`，新增项目不得写入绝对路径 |
| 在 `output.py` 中调用 `sys.exit()` | 破坏错误日志记录链 |
| 修改已发布的 API 响应结构（`success()`/`error()` 的 `status`/`data`/`error` 键名） | Agent 依赖固定 schema |
| 跳过链路约束直接执行排查命令 | 违反 seek 核心设计理念 |
| 提交前不运行 `python -m seek_cli version` 验证 CLI 可正常启动 | 防止引入语法错误 |

---

## 5. PR 合入检查清单

合入 `main` 前，逐项确认：

- [ ] 分支命名符合 `前缀/描述` 格式
- [ ] `capabilities.py` 已同步更新
- [ ] `SKILL.md` 的工作流契约和按需索引已检查；相关场景知识已更新到 reference
- [ ] 临时产物已通过 `scripts/seek_tmp.py` 放入独立 `.seek-tmp` 运行目录，正式产物已迁出
- [ ] `CHANGELOG` 已添加条目
- [ ] 新增公开函数有类型注解和 docstring
- [ ] 无 `sys.exit()` 在 `output.py` 之外的非 `main()` 函数中
- [ ] JSON 配置文件读取有 `encoding="utf-8"` 和异常处理
- [ ] 种子配置两份副本（`cli/config/projects.json` 与 `cli/seek_cli/resources/config/projects.json`）保持一致，且未新增本地绝对路径
- [ ] 链路定义两份副本（`cli/chains/default.json` 与 `cli/seek_cli/resources/chains/default.json`）保持一致
- [ ] `python3 -m unittest tests.test_doc_consistency tests.test_documentation` 通过（守护镜像一致、文档链接可解析、无硬编码计数、链路表与定义一致）
- [ ] subprocess 调用使用 list 传参、`shell=False`
- [ ] `grep "except\s*:"` 返回 0 匹配
