# Windows 侧验证手册（feite-selection）

> 本文档面向**从未接触过本项目**的 Windows 执行者（人或自动化 Agent），用于首次部署验证和后续回归。
> 你不需要理解业务背景，只需要按第 4 节顺序执行、按第 6 节格式回执。
> 所有命令都在 PowerShell 中执行，工作目录是仓库根目录（包含 `install-client.ps1` 的目录）。

---

## 1. 项目是什么（最少必要背景）

- `feite-selection` 是一个**私有**仓库，内容为亚马逊美国站选品控制台、严格筛选流水线、浏览器用户脚本。
- 控制台是**本机服务**，地址固定为 `http://127.0.0.1:8788`。**不得改用其他端口**：浏览器脚本的安装地址和回连地址都写死了 8788。
- 技术栈：
  - Python 3.11+：控制台后端 `console/server.py`，只能在 Windows 上运行；
  - Node.js 18+：生成 Excel 工作簿；
  - PowerShell：安装、启动、停止、校验脚本。
- 设计原则是 **fail-closed（失败即关闭）**：任何校验失败都应停下来报告，**不得**删除校验、修改脚本、跳过预检或换端口绕过。
- 所有部署脚本都是 **UTF-8 with BOM**。Windows PowerShell 5.1 读取无 BOM 的 `.ps1` 时会使用系统 ANSI 代码页（简体中文系统是 936/GBK），中文会被错误解码并破坏字符串配对，导致整份脚本解析失败。**不要用编辑器把脚本另存为"无 BOM"**；如果校验报缺少 BOM，直接重新 checkout 对应文件。
- PowerShell 5.1 调用原生程序（python / node）时**不会转义参数里的双引号**：`python -c 'print("x")'` 里的引号会被吞掉，代码被截断。本仓库的约定是内联代码**不使用双引号**——需要字符串字面量时用两个连续单引号，或把参数拆成独立实参。
- Excel 生成依赖 Codex Desktop 自带的私有 npm 包 `@oai/artifact-tool`，它在：
  `%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules`
  仓库不包含这个包，也不允许下载"替代包"。

## 2. 代码版本要求（先确认，再执行）

代码已推送到私有仓库 `origin/main`。当前基线提交是（包含 PowerShell 语法、编码与原生命令参数三类修复）：

```
5e91831 fix: keep inline Python snippets free of double quotes
```

更早的历史（doctor、venv、历史迁移等）都在 `main` 上，克隆即可获得，不必逐个核对。

**获取代码**（仓库是私有的，需要当前 GitHub 账号已被授权；登录由 Git Credential Manager 或浏览器完成，**不要把任何 token 粘贴到聊天、文件或回执里**）：

```powershell
git clone https://github.com/yuanzeli695-byte/feite-selection.git
cd feite-selection
git log --oneline -6
```

如果这台机器上已有旧检出：

```powershell
git fetch origin
git checkout main
git pull --ff-only
```

**执行前必须确认**：

1. `git merge-base --is-ancestor 5e91831 HEAD` 的退出码为 0，表示已包含 `5e91831` 这个修复提交。首次验证请直接使用包含它的最新 `main`，并在回执中写明实际的 `git log --oneline -1`；
2. `git status --short` 中没有已修改（`M`）的已跟踪文件。

- 任一条不满足：**停止并在回执中说明**，不要自行 merge / rebase / reset / push，也不要手工拼凑文件。
- 都满足：继续。

如果拿到的是不带 `.git` 的目录拷贝（非推荐方式），无法校验提交号；请在回执中注明"无 .git，未能校验提交号"，并以 `.\doctor.ps1` 的 `关键文件` 检查和 `.\tools\check-ps-syntax.ps1` 的实际结果作为代码完整性证据。

无论哪种方式，开始前都要确认：**没有未提交的本地修改**（有则先向负责人报告，不要擅自 stash 或丢弃）。

## 3. 安全红线（违反会导致回执作废）

1. **不要修改** `pipeline/scripts/` 下的任何 `.user.js`、`pipeline/config/protected_script_hashes.json`、`console/server.py`。
2. **不要删除或绕过**任何校验、预检、哈希检查。
3. **不要改动端口**：只能用 8788。
4. **不要复制或传播**浏览器配置、配对码、SellerSprite 凭据、token、密码。
5. 停止控制台**只能**用 `.\stop-client.ps1`（它会先核对 PID 归属，只停止本仓库的 `server.py`）。其他进程一律不要碰。
6. 除非明确要求，**不要用管理员权限**运行。
7. 回执中如出现完整路径，保留即可；如出现任何密钥/token/密码，**必须打码**。
8. 如果这台机器正在被实际业务使用，**先征得负责人同意再停止控制台**；停止生产实例只能用其自身脚本，禁止 `taskkill /F`。

## 4. 执行顺序（每一步都要保留原始输出）

建议全程开启转录，便于回执引用：

```powershell
Start-Transcript -Path (".\windows-validation-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
```

### 步骤 0：环境快照

```powershell
$PSVersionTable.PSVersion.ToString()
[System.Environment]::OSVersion.VersionString
(Get-CimInstance Win32_OperatingSystem).DisplayVersion
Get-Command python.exe, py.exe, node.exe -ErrorAction SilentlyContinue | Select-Object Name, Source
python -c "import sys; print(sys.version)" 2>&1
node --version 2>&1
Test-Path "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies"
Get-PSDrive C | Select-Object Used, Free
```

记录：PowerShell 版本（5.1 或 7.x）、系统版本、Python/Node 的可执行文件路径与版本、Codex 运行时目录是否存在、磁盘剩余空间。

注意：如果 `python.exe` 的路径位于 `WindowsApps` 下，那是 Microsoft Store 的占位别名，运行它会弹出商店而不是 Python。这种情况**直接记录路径即可**，不要继续用它执行命令，后面安装器会处理或给出明确报错。

### 步骤 0.5：允许本会话执行脚本

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

只影响当前 PowerShell 会话，不改系统策略。

### 步骤 1：PowerShell 语法自检（不需要任何运行时）

```powershell
.\tools\check-ps-syntax.ps1
```

预期：每个脚本一行 `[ OK ]`，最后一行是 `语法检查通过：N 个脚本。`（当前仓库共 14 个 `.ps1`，含 `pipeline\scripts` 下的 5 个）。

该工具检查四类问题：PowerShell 解析错误；含中文但没有 UTF-8 BOM（PS 5.1 会按 ANSI 解码）；两个在**任何** PowerShell 版本都会失败的写法——双引号内的 `$变量:`（会被当成作用域/驱动器限定符）、使用弯引号 `“ ”` 作为普通字符（会被当成字符串定界符）；以及**单引号字符串内含双引号并作为原生命令参数**（PS 5.1 会吞掉内层双引号，Python/Node 收到被截断的代码）。

若出现 `[FAIL]`，把对应的行号与错误原文完整记下，然后**停止后续步骤**。

### 步骤 2：安装（会创建 venv 并安装 Python 依赖）

```powershell
.\install-client.ps1
```

关注三件事：

1. 是否出现 `正在创建依赖隔离环境: ...\.runtime\venv`；
2. 结尾是 `依赖隔离: ...\.runtime\venv`（成功）还是 `依赖隔离: 未启用`（降级）；
3. 是否出现黄色警告 `无法创建 venv...`（若出现，记录完整原文）。

安装完成后读取工具链记录：

```powershell
Get-Content .runtime\toolchain.json -Raw
```

记录其中 `python`、`basePython`、`pythonIsolation`、`venvRoot`、`node` 五个字段的实际值。

如果安装报错：完整复制错误信息，并附上 `.runtime` 目录下若有生成的日志，然后**停止**。

### 步骤 3：可用性自检

```powershell
.\doctor.ps1
.\doctor.ps1 -Json | Out-File -Encoding utf8 .\doctor-report.json
```

预期 13 项检查。其中两项不要误判：

- `[WARN] 批准脚本一致性` —— **已知的预期结果**，表示严格预检里记录的脚本版本（0.4.6 / 0.3.7）落后于批准清单（0.4.6.4 / 0.3.8.13）。**它不是部署失败**，请原样记录，不要尝试修复。
- `[SKIP] 控制台服务` —— 此时控制台尚未启动，属于正常跳过。

其余各项应为 `[ OK ]`。任何 `[FAIL]` 都要记录其 `detail` 和 `->` 提示原文。

### 步骤 3.5：独占 8788（同一台机器验证时）

如果这台机器上已经跑着另一个控制台（例如生产实例），步骤 4–6 无法与它并存：**同一时刻 8788 只能被一个进程监听**。要让所有步骤在同一台机器完成，必须按下面的接管流程在维护窗口内临时让出端口。**没有业务方同意，不要执行本段。**

停产前先完成（都不需要 8788）：步骤 1、2、7、8，并跑一次步骤 3 记录基线——此时「端口 8788」会是 `[FAIL]`，属于环境事实，不是缺陷。

窗口内按顺序执行：

1. 在**生产项目自己的目录**里，用它自己的停止方式关闭控制台（通常是那个项目的 `stop-client.ps1`）。**不要用 `taskkill /F`**：生产数据库可能正在写入。
2. 等待 30 秒，确认端口没有被自动拉起：
   ```powershell
   Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue
   ```
   如果端口又出现监听，说明生产控制台被某个管理器（计划任务、Codex、桌面守护）自动重启。先停掉那个管理器，否则放弃同机验证并在回执中说明。
3. 端口空闲后，立即按顺序执行：步骤 3（重跑一次，端口项应变为 `OK`）→ 步骤 4 → 步骤 5 → 步骤 6。
4. 步骤 6 结束后确认 8788 空闲，立即用生产项目自己的启动方式恢复生产控制台。
5. 恢复验证：请求 `http://127.0.0.1:8788/api/overview` 返回 200，并确认原有批次列表仍在。

回执中必须记录：业务方批准情况、停机开始/结束时间、生产 PID、恢复验证结果。

> 两套环境的数据是隔离的：验证用的 checkout 有自己的 `console/data` 与 `pipeline/history`，接管端口不会读写生产项目的数据目录。

### 步骤 4：启动控制台

```powershell
.\start-client.ps1
```

预期：`控制台已启动: http://127.0.0.1:8788 (PID ...)`。

然后另开一个 PowerShell 窗口验证接口（`api/overview` 的字段以实际返回为准，不要假设）：

```powershell
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8788/api/overview" -TimeoutSec 5
$response.StatusCode
$payload = $response.Content | ConvertFrom-Json
$payload.PSObject.Properties.Name -join ', '
$payload | ConvertTo-Json -Depth 4
```

记录 HTTP 状态码、顶层字段名，以及任何与预检、浏览器配对、脚本版本相关的字段值（原文照抄，不要改写字段名）。

如果端口被占用：**不要换端口**。如果不是本项目的实例，按步骤 3.5 的接管流程处理；不能接管时记录占用进程信息（`Get-NetTCPConnection -LocalPort 8788 -State Listen` + 对应命令行），然后停止并报告。

### 步骤 5：停机前校验

```powershell
.\verify-client.ps1
.\verify-client.ps1 | Out-File -Encoding utf8 .\verify-report.json
```

记录输出 JSON 中的 `ok` 字段和 `checks` 各项。若 `ok` 为 false，逐项记录失败的检查与错误信息。

### 步骤 6：停止控制台

```powershell
.\stop-client.ps1
```

记录输出（预期：`控制台已停止 (PID ...)`）。确认 8788 不再监听：

```powershell
Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue
```

### 步骤 7：Artifact 隔离探测（关键决策输入）

这一步**只读**，不会修改任何东西。目的是判断 `@oai/artifact-tool` 是否自包含。

```powershell
$src = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool"
$probe = Join-Path $env:TEMP ("artifact-tool-probe-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force (Join-Path $probe "node_modules\@oai") | Out-Null
Copy-Item -Recurse $src (Join-Path $probe "node_modules\@oai\artifact-tool")
Write-Output ("size_bytes=" + ((Get-ChildItem -Recurse -File $src | Measure-Object Length -Sum).Sum))
Get-Content (Join-Path $src "package.json") -Raw
Push-Location $probe
node --input-type=module -e "import('@oai/artifact-tool').then(m => { const k = Object.keys(m); console.log('import_ok keys=' + k.length); console.log(k.slice(0, 20).join(',')); }).catch(e => { console.error('import_failed: ' + ((e && e.stack) || e)); process.exit(1); })"
Write-Output ("node_exit=" + $LASTEXITCODE)
Pop-Location
```

记录：

- 包的总体积（`size_bytes`）；
- `package.json` 里的 `name`、`version`、`license`、`dependencies`、`engines`；
- 导入是否成功、导出的键数量、前 20 个键名；
- 失败时的完整错误栈；
- `node_exit` 的值。

判定标准（供回执结论使用）：
- 在 Codex 目录**之外**导入成功，且键里包含 `Workbook` 与 `SpreadsheetFile` → 该包可考虑冻结到仓库私有 vendor 目录；
- 导入失败或依赖 Codex 内部路径 → 报告失败原因，暂不能冻结。

### 步骤 8：历史迁移演练（只读，不写入）

```powershell
.\export-client-history.ps1
.\import-client-history.ps1 -Archive <上一步生成的 zip 路径> -DryRun
```

记录：

- 导出的 zip 文件名、大小、打印的严格合格历史条数；
- DryRun 输出里的每条计划（`[新增]` / `[将覆盖，并先备份]`）。

**不要**去掉 `-DryRun`。真实导入需要负责人单独授权。

---

## 5. 如果出问题

- 控制台起不来：读取 `.runtime\console.stderr.log` 的最后 30 行，连同 `doctor.ps1` 的 `[FAIL]` 项一起附上。
- 语法检查报"含非 ASCII 字符但没有 UTF-8 BOM"：说明文件被编辑器重新保存过，用 `git checkout -- <文件>` 恢复原样，不要手工改编码。
- 语法检查报"双引号内的 `$变量:`"或"弯引号"：这是脚本自身的写法规避问题，记录后交给负责人，不要自行改写脚本。
- 端口被占用：只记录，不杀进程。
- venv 创建失败：记录完整警告；不要手工安装 `openpyxl`/`Pillow` 到系统 Python 来"绕过"，那会破坏隔离语义。
- 任何情况下都**不要**为了实现"通过"而修改脚本、删除检查或改端口。

---

## 6. 回执文档（必须按此结构填写）

> 用简体中文填写，保留原始输出的代码块。**不要转述错误信息，要原文粘贴。**
> 密钥、token、密码一律打码为 `<REDACTED>`。

```markdown
# feite-selection Windows 验证回执

## 0. 执行信息
- 执行时间（本地时区）：
- 执行人 / Agent：
- 仓库路径：
- git HEAD（`git log --oneline -1`）：
- git status 是否干净：是 / 否（否：贴出 `git status --short`）
- 是否启用了 Start-Transcript：是（文件：…）/ 否
- 是否执行了步骤 3.5（接管 8788）：是 / 否（是：停机开始/结束时间、生产 PID、恢复验证结果）

## 1. 环境快照
| 项目 | 值 |
|---|---|
| Windows 版本 | |
| PowerShell 版本 | |
| Python 路径 / 版本 | |
| py 启动器是否存在 | |
| Node 路径 / 版本 | |
| Codex 运行时目录是否存在 | |
| C 盘剩余空间 | |

## 2. 步骤结果总表
| 步骤 | 命令 | 退出码 | 结论（PASS/FAIL/SKIP） | 关键输出摘要 |
|---|---|---|---|---|
| 1 语法自检 | `.\tools\check-ps-syntax.ps1` | | | |
| 2 安装 | `.\install-client.ps1` | | | |
| 3 自检 | `.\doctor.ps1` | | | |
| 4 启动 | `.\start-client.ps1` | | | |
| 5 校验 | `.\verify-client.ps1` | | | |
| 6 停止 | `.\stop-client.ps1` | | | |
| 7 Artifact 探测 | node 导入 | | | |
| 8 历史演练 | export + import -DryRun | | | |
| 3.5 接管 8788（如适用） | 停产 / 恢复 | | | |

## 3. 安装详情
- 是否创建 venv：是 / 否
- 安装器输出原文（含 venv 相关行）：
```text
（粘贴）
```
- `.runtime\toolchain.json` 原文：
```json
（粘贴）
```

## 4. doctor 结果
逐项填写（状态取自 `[ OK ]/[WARN]/[FAIL]/[SKIP]`）：

| 检查项 | 状态 | detail |
|---|---|---|
| 关键文件 | | |
| Python 解释器 | | |
| Node.js | | |
| toolchain.json 一致性 | | |
| Python 运行依赖 | | |
| Excel 私有依赖 | | |
| 受保护脚本哈希 | | |
| 批准脚本一致性 | | |
| 严格预检 | | |
| 运行目录可写 | | |
| SQLite 可写 | | |
| 端口 8788 | | |
| 控制台服务 | | |

`doctor -Json` 是否已保存：是（文件名）/ 否

## 5. 服务验证
- `/api/overview` HTTP 状态码：
- 返回 JSON 关键字段（原文）：
```json
（粘贴关键字段）
```
- `verify-client.ps1` 的 `ok` 字段：
- 失败的检查项（如有）与原文：
```text
（粘贴）
```

## 6. Artifact 探测结果
- `size_bytes`：
- `package.json` 的 name / version / license / engines / dependencies：
```json
（粘贴相关字段）
```
- 导入结果：成功 / 失败
- 导出键数量与前 20 个键名：
- `node_exit`：
- 失败时的完整错误：
```text
（粘贴）
```

## 7. 历史迁移演练
- 导出文件名 / 大小：
- 严格合格历史条数：
- DryRun 计划原文：
```text
（粘贴）
```

## 8. 问题与排查
按出现顺序记录每个问题：现象、完整报错原文、你做过的排查、最终状态。

## 9. 三个事实回答（必答）
1. 本机实际安装/使用的 Collector 与 Runner 版本分别是多少？请给出文件路径与 `// @version` 行原文。
   - 提示：查看 `pipeline/scripts/` 下实际被浏览器安装的那两个 `.user.js`；如果使用了 `AMAZON_CONSOLE_PROJECT_ROOT`，以该目录为准。
2. 这台机器是否连接了外部正式项目目录？若有，路径是什么？`AMAZON_CONSOLE_PROJECT_ROOT` 是否设置？
3. venv 是否成功创建？若失败，原因与你看到的确切错误是什么？

## 10. 结论
- 是否存在阻断问题：是 / 否
- 阻断项清单（逐条）：
- 建议的下一步：

## 11. 附件清单
- [ ] `doctor-report.json`
- [ ] `verify-report.json`
- [ ] `.runtime\console.stderr.log`（如存在）
- [ ] 导出 zip 的文件名与大小
- [ ] Start-Transcript 生成的完整转录文件
- [ ] Artifact 探测的完整控制台输出
```

---

## 7. 明确不要做的事

- 不要 `git push`、`git merge`、`git reset`，不要修改任何代码或受保护脚本。
- 不要删除 `.runtime\venv` 来"重试"（除非回执中说明原因并得到负责人同意）。
- 不要为了通过检查而修改 `preflight.py`、`protected_script_hashes.json` 或任何校验逻辑。
- 不要把控制台换到 8790 或其他端口。
- 不要把 token、密码、密钥写进回执或上传到任何外部服务。
- 不要在正式业务进行中擅自停止控制台。

---

## 维护记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-10-26 | 1.5 | 新增步骤 3.5：同机验证时独占 8788 的接管与恢复流程 |
| 2026-10-26 | 1.4 | 基线前移到 `5e91831`（补上原生命令参数修复） |
| 2026-10-26 | 1.3 | 内联 Python 片段去除全部双引号，规避 PS 5.1 原生参数转义缺陷；检查器增加对应规则 |
| 2026-10-26 | 1.2 | 基线前移到 `218a7df`（语法与编码修复）；版本校验改为 `merge-base --is-ancestor` |
| 2026-10-26 | 1.1 | 补充 UTF-8 BOM 前置条件；语法检查覆盖 BOM、`$变量:` 与弯引号三类问题 |
| 2026-10-26 | 1.0 | 初版：首次部署验证流程、安全红线、回执模板；基线提交 `f874514` |
