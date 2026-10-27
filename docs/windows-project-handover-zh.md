# feite-selection 项目移交报告（Windows 侧接手）

- 日期：2026-10-26
- 移交方式：代码、文档、验证状态与后续决策权整体移交给 Windows 侧执行方
- 仓库：`https://github.com/yuanzeli695-byte/feite-selection`（私有）
- 当前 `main` HEAD：`96f1af8`
- 配套文档：`docs/windows-validation-manual-zh.md`（v1.5）

> 本报告假定读者从未参与过本项目。请先完整读完第 2、4 节，再开始操作。

---

## 1. 这个项目是什么

- 亚马逊美国站**选品控制台 + 严格筛选流水线 + 浏览器用户脚本**，只能在 **Windows** 上运行。
- 控制台是**本机服务**，地址固定 `http://127.0.0.1:8788`。**不得更换端口**：Bridge、Collector、Runner 三个用户脚本的回连地址写死在这个端口上。
- 设计原则 **fail-closed**：任何校验失败都应停下并报告，不得删除校验、改脚本绕过、换端口。
- Excel 生成依赖 Codex Desktop 自带的私有 npm 包 `@oai/artifact-tool`（路径在 `%USERPROFILE%\.cache\codex-runtimes\...`），仓库不包含、也不允许下载替代包。

## 2. 现在的状态（截至 `96f1af8`）

### 2.1 已完成的代码与文档

| 提交 | 内容 |
|---|---|
| `e04e018` | 新增 `doctor.ps1`：13 项可用性自检 |
| `d5ca1ec` | 安装器解释器探测加固（跳过 Windows 商店别名、版本解析不再抛转换异常） |
| `afb693b` | 严格历史导出/导入（`export-client-history.ps1` / `import-client-history.ps1`） |
| `e25ab0d` | Python 依赖隔离到 `.runtime\venv`，工具链记录新增 `basePython`/`pythonIsolation`/`venvRoot` |
| `7f1a4b4` | `server.py` 启动时从清单读取批准脚本；新增 `tools/check-ps-syntax.ps1` |
| `f874514` | doctor 增加「批准脚本一致性」检查（漂移报 WARN） |
| `61c8138` | 新增 Windows 验证手册 |
| `218a7df` | 修 `doctor.ps1` 的 `$Directory:` 与弯引号；8 个含中文脚本加 UTF-8 BOM；检查器 v2 |
| `e19090c` / `66f8938` | 手册基线前移（文档） |
| `5e91831` | 内联 Python 片段去除全部双引号（规避 PS 5.1 原生参数转义缺陷）；检查器 v3 |
| `96f1af8` | 手册新增步骤 3.5：同机独占 8788 的接管与恢复流程 |

### 2.2 验证进度（来自 Windows 侧两轮回执）

- **步骤 1（语法自检）已通过**：14 个 `.ps1` 全部 `[ OK ]`。
- **步骤 2（安装）上一轮被双引号问题阻断**，该问题已在 `5e91831` 修复，**尚未复验**。
- 步骤 3–8 尚未执行。
- **8788 被生产控制台占用**：PID 12428，来自 `C:\Users\13045\Documents\亚马逊电商选品\automation_console\server.py`；该机处于实际业务使用中。
- 受保护脚本三份哈希与清单一致（Bridge / Collector / Runner 全部 MATCH）。

### 2.3 环境事实（务必保留）

| 项 | 值 |
|---|---|
| Windows | 11 教育版 Build 26200 |
| PowerShell | 5.1.26100（**没有 PowerShell 7**） |
| ANSI 代码页 | 936（GBK）——这是脚本必须带 UTF-8 BOM 的原因 |
| Python | PATH 3.14.4；Codex 自带 3.12.14（安装器优先选它） |
| Node | PATH v24.15.0；Codex 自带 v24.22.1 |
| Codex 运行时目录 | 存在 |
| `AMAZON_CONSOLE_PROJECT_ROOT` | 未设置 |

## 3. 本轮修复的三类缺陷（供你判断同类问题）

1. **编码**：PS 5.1 读取无 BOM 的 `.ps1` 时使用 ANSI 代码页，中文会破坏字符串配对。所有含非 ASCII 的脚本现在都带 BOM。
2. **词法**：双引号内的 `$变量:` 会被当成作用域限定符；弯引号 `“ ”` 会被当成字符串定界符。
3. **原生参数**：PS 5.1 向 python/node 传参时**不转义参数内的双引号**，内联代码会被截断。现在所有内联 Python 片段**不含任何双引号**。

`tools/check-ps-syntax.ps1`（v3）已覆盖以上三类 + 解析错误，共 14 个脚本。**任何修改脚本的动作之后，先跑它。**

## 4. 权限与边界（移交后的授权范围）

### 4.1 你被授权

- 修改本仓库的代码、脚本与文档；
- 提交并推送到 `main`（或按需建分支）；
- 运行全部验证步骤，包括在维护窗口内接管 8788；
- 在业务方批准的前提下，停止并恢复生产控制台；
- 依据本报告第 6 节做出技术判断，并把决定写入回执。

### 4.2 仍然禁止

- **force push、改写历史、删除仓库或分支**；
- 修改 `pipeline/scripts/*.user.js` 三个受保护脚本（会破坏哈希清单，必须重新走批准流程）；
- 修改 `protected_script_hashes.json` 里的 sha256（除非获得明确批准并同步更新 `server.py` 的校验逻辑）；
- 更换控制台端口（只能 8788）；
- 复制或传播浏览器配置、配对码、SellerSprite 凭据、token、密码；
- 用 `taskkill /F` 结束生产控制台；只能用生产项目自己的停止方式；
- 在未获业务批准时停止生产实例；
- 删除或绕过任何校验、预检、哈希检查。

### 4.3 保护文件清单（改动需谨慎并单独提交）

`console/server.py`、`pipeline/scripts/preflight.py`、`pipeline/config/protected_script_hashes.json`、`console/data/`、`pipeline/history/`。

## 5. 建议的执行顺序

### 阶段 A：窗口前（不需要 8788）

1. `git pull --ff-only`，确认 `git merge-base --is-ancestor 5e91831 HEAD` 返回 0；
2. `.\tools\check-ps-syntax.ps1` → 14 个 `[ OK ]`；
3. `.\install-client.ps1` → 记录是否创建 `.runtime\venv`、`toolchain.json` 全文；
4. `.\doctor.ps1` → 记录基线（端口项会是 `[FAIL]`，属于环境事实）；
5. 步骤 7 artifact 探测（只读）；
6. 步骤 8 历史导出 + `-DryRun`（只读）。

**只有阶段 A 全绿（端口项除外）才进入阶段 C。**

### 阶段 B：2 分钟彩排（强烈建议）

选业务空闲的几分钟：停生产 → 确认 8788 空闲 → 立刻按原方式启动 → 验证 `/api/overview` 200。**不跑验证**。

目的：确认恢复路径可用、确认没有守护进程自动重启、量出真实停机耗时。彩排失败则同机验证方案不成立。

### 阶段 C：维护窗口（按手册步骤 3.5）

1. 备份生产数据库（复制其 `console/data/console.db` 到带时间戳的副本）；
2. 用生产项目自己的脚本停止生产控制台；
3. 等 30 秒确认 8788 空闲（防止被自动拉起）；
4. 依次执行：`doctor`（端口项应变 `OK`）→ `start-client` → `verify-client` → `stop-client`；
5. 确认 8788 空闲后立即恢复生产；
6. 验证 `/api/overview` 200、原有批次列表仍在；
7. 回执记录停机起止时间、生产 PID、恢复证据。

### 阶段 D：不阻塞的长期项

- **CI**：GitHub Actions `windows-latest` 跑 `check-ps-syntax` + `pytest pipeline/tests`（无需 Codex）；
- **probes 重构**：把 6 段内联 Python 抽到 `tools/probes/*.py`；
- **P0-1**：依据阶段 A 的 artifact 探测结果决定是否把 `@oai/artifact-tool` 冻结为带 SHA-256 的私有 tgz；
- **P0-2 第二步**：把 `preflight.py` 的批准版本从 0.4.6/0.3.7 对齐到清单的 0.4.6.4/0.3.8.13（**需先确认正式项目实际安装版本**）。

## 6. 待决策事项

| # | 事项 | 建议 |
|---|---|---|
| 1 | 是否停止生产实例、窗口时段 | 业务方批准后执行；先做阶段 B 彩排 |
| 2 | P0-2 是否对齐预检批准版本 | 先确认生产项目实际装的 Collector/Runner 版本；对齐会改变验收口径 |
| 3 | P0-1 是否冻结私有包 | 看阶段 A 的探测结果：能在 Codex 目录外导入且含 `Workbook`/`SpreadsheetFile` 才可冻结 |
| 4 | 是否启用 CI | 建议启用（不阻塞验证） |

> **重要澄清**：`approvedPair.bridge = 2.1.3` 是**桥协议版本**，`browser_bridge_v2.user.js` 的 `@version 2.1.6` 是**用户脚本版本**，服务端分别校验。**不要**把清单改成 2.1.6。

## 7. 关键文件地图

| 文件 | 作用 |
|---|---|
| `install-client.ps1` / `start-client.ps1` / `stop-client.ps1` / `verify-client.ps1` | 部署入口 |
| `doctor.ps1` | 13 项可用性自检（`-Json` 输出机器可读报告） |
| `export-client-history.ps1` / `import-client-history.ps1` | 严格历史迁移（导入必须先用 `-DryRun`） |
| `tools/check-ps-syntax.ps1` | PowerShell 语法与陷阱检查（v3） |
| `console/server.py` | 控制台后端（Windows 专用） |
| `pipeline/config/protected_script_hashes.json` | 批准脚本清单（版本 + SHA-256） |
| `pipeline/scripts/preflight.py` | 严格预检（只读） |
| `docs/windows-validation-manual-zh.md` | 验证手册（v1.5，含步骤 3.5） |

## 8. 环境与网络注意事项

- 这台机器上有两套东西：验证用的 checkout（`D:\01-开发\feite-selection`）和生产项目（`C:\Users\13045\Documents\亚马逊电商选品`）。**两者数据目录、`.runtime` 完全独立**，只有 8788 端口共享。
- 从中国大陆网络访问 `github.com` 可能解析到不可达 IP（`api.github.com` 往往可用而 `github.com` 不可用）。若 `git push` 卡住，先用 `curl -sI https://github.com` 判断，必要时开启代理（Throne/Clash）再重试。
- 沙箱/Linux 侧无法运行 PowerShell，**所有验证结论以 Windows 实测为准**。

## 9. 已知风险与未完成项

1. 步骤 2–8 尚未在修复后复验（本轮修复未经真实 Windows 运行）；
2. 8788 被生产实例占用，步骤 4–6 必须按步骤 3.5 处理；
3. P0-1 / P0-2 未完成；
4. 停产前运行 doctor，端口项必然 `[FAIL]`——这是预期，不是缺陷；
5. 生产控制台若被守护进程自动拉起，同机验证不成立，需要先停守护。

## 10. 回执要求

沿用 `docs/windows-validation-manual-zh.md` 第 6 节的 11 小节模板，并额外包含：

- 阶段 A / B / C 各自的结果与耗时；
- 停机起止时间、生产 PID、恢复前后 `/api/overview` 的对比；
- 第 6 节四个待决策事项的结论（或"待业务确认"）；
- 本次是否改动了代码；若有，逐条列出提交号与原因。

## 11. 交接确认

接手方在本报告基础上继续推进，视为已确认：

- 已阅读本报告与验证手册 v1.5；
- 理解并接受第 4 节的权限与边界；
- 知悉生产实例的保护要求与 8788 的独占约束；
- 同意用第 10 节的格式回报结果。
