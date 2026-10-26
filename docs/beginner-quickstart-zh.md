# 选品台新手安装与首次运行

这份说明给第一次接触项目的人使用。请按顺序执行，不要把旧电脑的
`console/data`、浏览器配置、配对码或导出文件复制到新电脑。

## 需要准备

1. Windows 10/11 电脑。
2. Git，并且当前 GitHub 账号已被授权访问私有仓库
   `yuanzeli695-byte/feite-selection`。
3. Codex Desktop。首次运行前请打开一次，让它完成本机运行时初始化；
   Excel 构建依赖 Codex 自带的私有 `@oai/artifact-tool`，仓库不会公开或
   替换这个组件。
4. Python 3.11 或更高版本、Node.js 18 或更高版本。安装器会优先使用
   Codex 自带版本，也接受系统版本。
5. Chrome，以及 ScriptCat 或 Tampermonkey 浏览器脚本管理器。
6. 可登录 Amazon US 和 SellerSprite 的账号。正式运行前要在 Amazon 选择
   美国配送地址，并自行处理登录失效或 CAPTCHA。

## 第一次安装

在 PowerShell 中执行：

```powershell
git clone https://github.com/yuanzeli695-byte/feite-selection.git
cd feite-selection
Set-ExecutionPolicy -Scope Process Bypass
.\install-client.ps1
```

GitHub 登录提示由 Git Credential Manager 或浏览器完成。不要把密码、令牌
或 SellerSprite 密钥粘贴到聊天、Issue 或仓库文件中。

安装器会创建空的运行目录和严格历史文件，安装 `openpyxl`、`Pillow`，并
把 `pipeline/node_modules` 安全地连接到当前 Codex 运行时。它不会导入其他
机器的批次、账号、浏览器会话或配对码。

如果提示缺少 `@oai/artifact-tool`，先打开 Codex Desktop 并等待初始化完成，
再重新执行安装器；不要下载来历不明的替代包，也不要使用
`-SkipDependencyInstall` 作为正式运行方案。

## 启动与自检

新电脑上第一次部署，先运行可用性自检：

```powershell
.\doctor.ps1
```

它逐项验证“能不能真的干活”：Python/Node 版本（会识别 Windows 商店的占位
别名）、`openpyxl`/`Pillow` 能否导入、Codex 私有 Excel 组件
`@oai/artifact-tool` 能否真实导入、受保护脚本的 SHA-256、严格预检、运行目录
与 SQLite 是否可写，以及 8788 端口当前属于哪个进程。每项失败都会打印一条
以 `->` 开头的修复提示。

- `.\doctor.ps1 -Json`：输出机器可读的 `feiteClientDoctor/v1` 报告。
- `.\doctor.ps1 -NoServiceCheck`：客户端尚未启动时跳过服务检查。

退出码 `0` 表示没有阻断项（可能有警告），`2` 表示存在阻断问题。自检通过后再启动：

```powershell
.\start-client.ps1
.\verify-client.ps1
```

浏览器打开 `http://127.0.0.1:8788`。正式流程固定使用 `8788`，不要改成
`8790`，因为批准的 Bridge、Collector、Runner 和脚本安装地址都回连这个端口。

关闭选品台时执行：

```powershell
.\stop-client.ps1
```

停止脚本会核对 PID 是否属于本仓库的 `console/server.py`，不会主动结束其他
程序。

## 安装并配对浏览器脚本

1. 在 SellerSprite 产品研究页登录后，在 ScriptCat/Tampermonkey 安装
   `http://127.0.0.1:8788/seller-sprite-bridge.user.js`。
2. 回到选品台，按页面提示复制一次性配对码，在 SellerSprite Bridge 面板中
   完成配对。
3. 在 Amazon US 商品页安装
   `http://127.0.0.1:8788/browser-bridge.user.js`，再用选品台显示的配对码
   完成右下角 Bridge 配对。
4. 确认版本为 Bridge `2.1.3`、Collector `0.4.6.4`、Runner `0.3.8.13`。
   `0.3.8.12` 只保留作历史资料，不能安装或用于正式运行。

如果 Bridge 显示无法连接，先确认选品台仍在运行、地址是 `8788`，再从本地
地址重新安装脚本；不要同时启用旧版和新版 Bridge。

## 第一次只跑小规模 smoke

首次不要直接导入一大批类目：

1. 先只导入一个 Amazon US 类目并创建一个批次。
2. 等 SellerSprite 导出文件回传，确认候选分析表有内容。
3. 只选择一个 ASIN，导入 Runner 并筛选。
4. 等待 Runner JSON 回传，在第 03 区粘贴合并 JSON。
5. 只有“校验粘贴 JSON”通过并且生成按钮可用时，才生成 direct-import Excel。
6. 检查运行记录、候选数量、JSON 指纹和 Excel 文件。正式放量前还需要完成
   至少 30 个真实 ASIN 的配对证据。

任何缺少价格、尺寸、流量、主图、来源文件或版本证据的情况都会停在待确认，
这是严格门禁的正常行为，不要手工把状态改成通过。

## 常见问题

### 8788 已被占用

不要换端口启动正式流程。先检查监听者：

```powershell
$listenerPid = (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8788 -State Listen).OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" |
  Select-Object ProcessId,CommandLine
```

只有确认命令行属于当前仓库的 `console/server.py` 时，才运行
`.\stop-client.ps1`。其他程序保持运行，并联系电脑管理员解决端口冲突。

### `verify-client.ps1` 失败

先阅读输出中的具体检查项。哈希、严格预检、依赖或版本任一失败，都不能
继续正式选品；不要删除校验、替换脚本或跳过预检。

### `doctor.ps1` 报“Excel 私有依赖”失败

按提示先打开 Codex Desktop，等本机运行时初始化完成后重新运行
`install-client.ps1`，再重跑 `doctor.ps1`。不要下载来历不明的替代包，
仓库也不会用其他组件替换这个私有包。

### SellerSprite 导出失败或页面反复刷新

确认 SellerSprite 登录有效、Amazon US 地址正确、Bridge 配对状态在线，并且
导出记录确实生成了 `.xlsx`、`.csv` 或 `.tsv`。站点失败时使用人工回退上传，
不要伪造导出文件。

## 安全与回滚

仓库保持 Private，不要添加未批准的协作者。批次数据库、运行历史、浏览器
配置、配对码、凭据、导出文件和 Excel 都保存在本机且被 Git 忽略。

回滚时先停止客户端，再切换到上一个 Git 提交并重新运行安装器：

```powershell
.\stop-client.ps1
git log --oneline -5
git switch --detach <已确认的提交>
.\install-client.ps1
```

不要回滚或修改受保护的 Bridge、Collector、Runner 文件来解决业务数据问题。
