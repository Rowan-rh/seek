# Tasks: standardize-seek-tmp-layout

## 1. 临时工作区工具

- [x] 1.1 新增仓库级 `.seek-tmp` 运行目录创建 helper，固定 UTC 日期、运行标识和四阶段目录
- [x] 1.2 写入 schema version 1 manifest，并提供成功 JSON 与失败非零退出码
- [x] 1.3 保证并发/同秒同 slug 创建不覆盖既有运行目录，失败时不残留半成品目录

## 2. 规范与仓库卫生

- [x] 2.1 在 `.gitignore` 中忽略 `.seek-tmp/`
- [x] 2.2 在 `AGENT.md` 中增加临时产物强制规则及与 `SEEK_HOME`、系统临时目录、原子写文件的边界
- [x] 2.3 在根 README 中记录目录结构、helper 用法和正式产物迁出要求

## 3. 测试与验证

- [x] 3.1 增加 helper 的结构、manifest、slug 校验、同秒冲突和 CLI JSON 测试
- [x] 3.2 增加 `.gitignore` 与文档契约一致性测试
- [x] 3.3 运行相关单测、文档一致性测试、OpenSpec strict 校验和仓库 PR 检查
