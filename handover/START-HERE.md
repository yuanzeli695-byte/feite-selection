# START-HERE · feite-selection 项目接手

> 这个文件夹**就是项目仓库本身**（含完整 git 历史，HEAD `882210f`），2026-10-30 从 Linux 机器整体迁移到 Windows 11 继续验证与整改。
> **新机 Claude：请先读完本页，再读 `handover/session-summary-2026-10-30.md`。**

**如果你是把文件夹拖进 Claude 的人**：直接发一句
`请阅读 START-HERE.md，接手 feite-selection 的后续任务。`

---

## 你拿到的是什么

- 当前目录 = 仓库工作区，**不需要重新 clone**；
- `handover/` 是本轮迁移的上下文（会话摘要、回执要点、环境说明）；
- `docs/windows-project-handover-zh.md` 是正式移交报告（权限边界与阶段计划）；
- `docs/windows-validation-manual-zh.md` 是逐步验证手册（v1.5，含步骤 3.5）。

## 第 1 步：确认仓库可用

```powershell
git status -sb
git log --oneline -1
git merge-base --is-ancestor 5e91831 HEAD
echo "ancestor_exit=$LASTEXITCODE"
```

预期：工作区干净；HEAD 为 `882210f`；`ancestor_exit=0`。

如果报 `dubious ownership`（目录所有者与当前用户不一致）：

```powershell
git config --global --add safe.directory "<本目录的绝对路径>"
```

## 第 2 步：身份与凭据

```powershell
git config user.name "yuanzeli695-byte"
git config user.email "yuanzeli695@gmail.com"
```

- 远端已指向 `https://github.com/yuanzeli695-byte/feite-selection.git`；
- 推送认证用 **Git Credential Manager 或新机自己的 PAT**；
- **不要复制旧机器的任何 token**，也不要复制浏览器配对码。

## 第 3 步：语法自检（必做）

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\tools\check-ps-syntax.ps1
```

预期：14 个 `.ps1` 全部 `[ OK ]`，末行 `语法检查通过：14 个脚本。`

## 第 4 步：按顺序阅读

1. `handover/session-summary-2026-10-30.md` —— 先建立全局认识；
2. `docs/windows-project-handover-zh.md` —— 权限与四阶段计划；
3. `docs/windows-validation-manual-zh.md` —— 每一步的具体命令；
4. `handover/windows-receipts-summary.md` —— 前几轮验证踩过的坑。

## 第 5 步：继续任务

按移交报告的阶段推进：

1. **阶段 A（不需要 8788）**：语法检查 → `install-client.ps1`（`.runtime\venv` + 冻结包解压到 `.runtime\node_modules`）→ doctor 基线 → 步骤 7 artifact 探测 → 步骤 8 历史 DryRun；
2. **阶段 B（2 分钟彩排）**：停生产 → 确认 8788 空闲 → 立即恢复 → 验证 `/api/overview`；
3. **阶段 C（维护窗口）**：按手册步骤 3.5 接管 8788，跑完步骤 3–6 后恢复生产；
4. **阶段 D**：CI、probes 重构、私有包冻结、预检对齐已由 Windows 侧完成；剩余是**补齐验证证据**（单 ASIN live smoke、paired-30）与私有包分发方式的决策。

## 重要注意事项

- 项目只能在 **Windows** 上运行；原 Linux 机器只用于改代码和静态检查。
- 生产控制台占用 8788（PID 12428，来自 `C:\Users\13045\Documents\亚马逊电商选品`）。**未获业务批准不得停机**，且只能用生产项目自己的脚本停止，禁止 `taskkill /F`。
- 停产前跑 doctor，「端口 8788」必然是 `[FAIL]`，这是环境事实，不是缺陷。
- 「批准脚本一致性」现在应为 `[ OK ]`（预检已对齐到 0.4.6.4 / 0.3.8.13）；若出现 `[WARN]`，说明再次漂移，原样记录并停止。
- `approvedPair.bridge = 2.1.3` 是桥**协议**版本，用户脚本 `@version 2.1.6` 是**脚本**版本，两者不要互相替换。
- 需要与远端同步时用 `git pull --ff-only`；出现冲突先报告，不要 `reset --hard`。
