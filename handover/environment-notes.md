# 环境与凭据说明

## 原机器（迁移来源）

- Linux（Ubuntu / LXQt），**没有 PowerShell**，项目无法在原机运行。
- 原机只用于：读代码、改代码、静态检查（括号配平、规则镜像）、提交与推送。
- **所有运行验证都必须在 Windows 机上完成。**

## 新机器（Windows 11）需要具备

| 组件 | 要求 | 说明 |
|---|---|---|
| Windows PowerShell | 5.1（自带）或 7.x | 脚本按 5.1 兼容编写 |
| Git for Windows | 任意近期版本 | 用于 pull/push |
| Python | 3.11+ | 安装器优先使用 Codex 自带版本 |
| Node.js | 18+ | 同上 |
| Codex Desktop | 已初始化本机运行时 | 提供私有包 `@oai/artifact-tool` |

## 提交身份（与仓库历史一致）

```
user.name  = yuanzeli695-byte
user.email = yuanzeli695@gmail.com
```

在本目录执行：

```powershell
git config user.name "yuanzeli695-byte"
git config user.email "yuanzeli695@gmail.com"
```

## 凭据

- 原机的 GitHub token（`~/.config/github-mcp/token`）**没有**随项目迁移，也不应该复制。
- 新机请用 **Git Credential Manager** 或自己的 PAT 认证；若需要 GitHub MCP，在新机重新配置。
- 浏览器的配对码、SellerSprite 凭据同理：不迁移、不复用。

## 网络

- 原网络环境下 `github.com` 曾解析到**不可达 IP**，而 `api.github.com` 正常；开启代理（Throne / Clash）后恢复。
- `git push` 卡住时，先判断连通性再重试：

```powershell
curl.exe -sI https://github.com -o NUL -w "%{http_code}`n"   # 200/301 为通
```

## 运行数据

- 迁移不包含 `.runtime`、`console/data`、`pipeline/history` 或任何 Excel 产物。
- 需要迁移严格合格历史时，用仓库里的 `export-client-history.ps1` / `import-client-history.ps1` 单独处理。
