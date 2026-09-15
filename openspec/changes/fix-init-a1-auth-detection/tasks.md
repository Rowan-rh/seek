## 1. 代码修复

- [x] 1.1 `A1_CONFIG` 探测路径改为 `~/.config/a1/auth.yaml`
- [x] 1.2 `--verify` 成功回写 `configured=true`；认证失败/进程异常回写 `configured=false`
- [x] 1.3 保持默认（不 verify）分支的本地文件探测语义与输出结构不变

## 2. 测试加固

- [x] 2.1 隔离现有测试对宿主机 `~/.config/a1/` 的隐式依赖（mock A1_CONFIG）
- [x] 2.2 新增：auth.yaml 存在时默认不误报 needs_auth、顶层 ready=true
- [x] 2.3 新增：verify 成功 A1 configured=true；verify 失败即使凭据文件存在也 configured=false 且 ready=false

## 3. 版本与验证

- [x] 3.1 版本 0.10.0 → 0.10.1，补 CHANGELOG 与 SKILL.md cli_version_ref
- [x] 3.2 运行全量单元测试
- [x] 3.3 `openspec validate fix-init-a1-auth-detection --strict`
- [x] 3.4 端到端 `seek init` / `seek init --verify` 验证误报消失
