# Tasks: improve-harness-readiness

## 1. 运行目录隔离

- [x] 1.1 新增 `seek_cli/paths.py`，实现 `SEEK_HOME` 优先、`~/.seek` 默认的统一路径解析
- [x] 1.2 将 config/settings/chain/db/log/perf/旧配置/version 等 seek 自有状态切换到统一路径
- [x] 1.3 调整 CLI 启动顺序，保证 `--help` 不创建版本文件或 seek home
- [x] 1.4 新增默认路径兼容、隔离路径写入和帮助无副作用测试

## 2. Harness 就绪检查

- [x] 2.1 新增 `seek harness check` 命令及 parser 路由
- [x] 2.2 实现存储、内置资源、链路模板、版本、外部命令和 HTTP 配置的离线检查与分级结果
- [x] 2.3 同步 capabilities、命令文档和单元测试

## 3. 安全与版本门禁

- [x] 3.1 在 SKILL 硬约束中加入外部证据不可信和提示词注入防护规则
- [x] 3.2 增加 Skill `cli_version_ref` 与运行时版本的仓库强一致测试
- [x] 3.3 修正文档中的本机绝对路径与过期 repoPath 表述

## 4. 离线评测与 PR 检查

- [x] 4.1 新增 `harness/run_evals.py`，以临时 `SEEK_HOME` 执行确定性 CLI 黑盒场景并输出 JSON
- [x] 4.2 将 `cli/run_checks.sh` 升级为隔离环境下的全量测试、Harness 评测和静态检查入口
- [x] 4.3 补齐 Harness runner 的成功与失败行为测试

## 5. 版本与验证

- [x] 5.1 升级 CLI 版本并补充 CHANGELOG，同步 `SKILL.md#cli_version_ref`
- [x] 5.2 运行 OpenSpec validate、全量单测、Harness eval、PR 检查和 CLI 冒烟
- [x] 5.3 归档 OpenSpec change，提交功能分支并合入 develop
