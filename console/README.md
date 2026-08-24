# Amazon 选品流水线控制台

本机地址：`http://127.0.0.1:8788`

## 预检缓存与页面刷新

`preflight-cache-v1.0.0` 将完整严格预检从每 5 秒一次的 `/api/overview` 页面刷新热路径移到进程内缓存和单飞后台任务。首次打开或缓存超过 45 秒时，页面立即返回上一次结果（没有结果时返回保守的检查中占位），后台只启动一个预检任务；失败会保留旧结果并显示失败/过期状态，带 10 秒退避。`preflightMeta` 提供状态、最近检查时间、年龄和错误信息。缓存只用于页面展示，候选派发、正式启动和手动 `/api/preflight` 仍执行同步预检，不会用过期结果放行严格流程。

临时回滚时，在启动控制台前设置 `AMAZON_CONSOLE_PREFLIGHT_CACHE=0`，即可恢复 `/api/overview` 的同步预检行为；重启控制台后生效。`AMAZON_CONSOLE_PREFLIGHT_CACHE_TTL` 可调整展示缓存 TTL（秒，最小 15 秒）。

## 启动

```powershell
cd C:\Users\13045\Documents\亚马逊电商选品
.\automation_console\start.ps1
```

Windows 子进程窗口策略为 `windows-no-console-v1.0.0`。控制台默认使用 `CREATE_NO_WINDOW` 启动预检、流水线和工作簿构建子进程，避免页面轮询时闪出命令行窗口。临时回滚时，在启动控制台前设置 `AMAZON_CONSOLE_WINDOWS_NO_CONSOLE=0`。

## 本地任务恢复

`local-job-recovery-v1.0.0` 将候选准备和 direct_import Excel 的本地子进程租约写入 `local_job_leases`：包括批次、阶段、attempt、PID、命令摘要、运行目录、日志路径和控制台实例。正常退出会写入退出码；启动时会扫描上一实例的 `starting/running` 租约。

恢复策略默认关闭失败：服务重启后不会按裸 PID 自动接管、强杀或猜测产物是否完成。进程不存在时，阶段变为“待确认”，保留输入、日志和产物路径，并显示“从中断任务重试”；进程仍存在或无法确认归属时，阶段标记为遗留任务，重试会被阻止，直到用户确认该进程已经结束。显式重试仍重新执行原有同步严格预检、候选输入校验、JSON 指纹和 Excel 输入契约；旧回调不能覆盖新 attempt。

Browser Bridge / Runner 属于外部会话，不纳入本地 PID 接管；它们仍仅依据现有 token、版本、commandId、executionMode、batchName、queueHash 和心跳租约恢复。该机制只解决重启后不再假报本地任务“运行中”，不改变 A-F、历史去重或最终放行规则。

控制台绑定正式项目 `C:\Users\13045\Desktop\amazon_products`，当前候选来源默认使用 `browser_export`：子账号在 SellerSprite 网页按类目由 SellerSprite Bridge 自动执行严格查询并回传 `.xlsx/.csv/.tsv`，控制台校验完整查询 URL 后复用正式严格预筛、历史去重、主图和候选分析表流程。`official_api` 仍保留为可选模式，但需要主账号 Open API 密钥。当前技术适配 Browser Bridge 协议 `2.1.3` / 脚本 `2.1.6`、Collector `0.4.6.4`、Runner `0.3.8.13` 和 SellerSprite Bridge `1.0.4`；Collector/Runner 仍是候选组合，正式放量前需要完成单 ASIN 现场 smoke 与不少于 30 个真实 ASIN 的配对证据。全局类目池、批次、命令、事件、浏览器会话和产物索引保存在 `automation_console/data/console.db`；正式运行产物保存在正式项目的 `runs/<runId>/`。

## 三段流程

1. 在页面顶部的全局“类目池”一次粘贴多行类目，支持 `类目名称`、`nodeIdPath`、`类目名称 | nodeIdPath` 三种格式。系统按大小写不敏感方式去重，并记录“未使用 / 已分配 / 已完成”。从某个未使用类目点击“创建批次”后，该批次只会领取这一条；已领取条目不能被第二个批次重复使用。浏览器导出模式会在批次创建时自动把任务下发给 SellerSprite Bridge；Bridge 逐个查询、导出并回传后，最后一个文件会自动启动正式严格预筛、下载主图并生成候选分析表。没有 Bridge、登录失效、URL 条件放宽或导出文件证据不完整时停在 `needs_attention`，候选面板默认显示自动状态，仍可展开“人工回退上传”。
2. 审核候选分析表并确认 Runner 队列。点击“导入 Runner 并筛选”后，Browser Bridge v2 会自动填写批次名称、操作人、目标数和 ASIN 队列，随后启动 Runner。控制台实时接收心跳、进度、当前 ASIN、门槛和异常事件。
3. Runner 完成后，Bridge 回传带版本元数据的合并 JSON。点击“复制合并 JSON”，再手工粘贴到 03 区。控制台解析并标准化两份 JSON，只在标准化产物 SHA-256 一致时允许生成 Excel；启动生成前还会重新核验源文件和已粘贴文件的指纹，并拒绝任何路径覆盖。控制台只接受明确的 `directImport=true`、`importMode=browser-qualified` 摘要；任何显式 `importMode` 都必须配套布尔值 `directImport=true`，缺失、未知或类型错误均关闭失败。Excel 运行期间，相同 Runner JSON 只作为幂等请求忽略，不同 JSON 不得替换当前原件；任务槽一直保留到工作簿解析完成，重复启动会被拒绝，完成前后都会复核启动时锁定的源/粘贴路径和指纹。产物工作表和文件名使用 `Runner通过_未做A-F验收` / `runner_candidates_unaccepted_*`，不会冒充 A-F 最终严格验收，也不会更新严格合格历史。完成时还要求候选数据、运行摘要和 Excel 的实际 SHA-256 均与构建报告一致，且 `finalXlsx` 是当前回放目录的直接子文件并带未验收标记；没有旧文件名或目录外文件回退。构建器通过 `runner-unaccepted-workbook-v1.0.0` 执行这一标记；将 `AMAZON_RUNNER_UNACCEPTED_LABELS_V1=0` 会保守地禁用直接导入工作簿输出，而不是恢复不安全的“最终合格品”标签。

03 区使用 `json-handoff-draft-v1.0.0` 在当前页面会话中按“批次 ID + Runner 原件 SHA-256”保留尚未校验的 JSON 草稿；5 秒轮询、SSE 更新和手工刷新重建面板时会恢复内容、焦点、选区和编辑区滚动位置。原件指纹改变会丢弃旧草稿，校验请求互斥，失败时保留草稿，成功时清理草稿。草稿只解决前端刷新覆盖，不参与 SHA-256 校验，也不能解锁 Excel。回滚时将 `static/json-handoff-draft.js` 中的 `ENABLED` 设为 `false`；后端标准化 JSON 指纹门槛保持不变。

## 已完成选品类目库与可恢复批量删除

`category-repository-v1.1.0` 默认开启。控制台会把 Amazon US 中状态为 `completed` 且三个流程阶段都为 `completed` 的批次幂等登记到“已完成选品类目库”，并在启动时回填历史完成批次。类目库口径固定为 `console_completed_runner_unaccepted`，界面明确显示“Runner 已筛选，未做 A-F 最终验收”；类目库命中只说明该类目曾跑完当前控制台流程，不代表严格合格或最终放行，也不会写入严格合格历史。未完成、失败或已停止批次即使被删除，也不会进入完成类目库。

左侧批次列表为每个可删除批次提供复选框、单项删除、“全选可删除”和“删除所选”。完成、失败、已停止、待处理及尚未开始的批次都可执行可恢复删除；批量请求是原子的，任一所选批次不可删除时整批不产生变化。正在运行或停止、有本地任务、活跃浏览器命令、已连接 Browser Bridge 或未结束外部派发的批次会保持禁用，并返回具体阻止原因，必须先完成停止流程。

可恢复删除只写独立归档状态和功能审计，不修改批次 payload、阶段结果、时间戳、运行日志或任何已落盘产物。未完成批次删除时保留其类目池所有权，并把对应条目与批次一起从当前视图隐藏；恢复后原绑定和条目一起重新显示，因此类目不会被其他批次重复领取，功能开关回滚时也不会形成双重归属。删除后的批次可在“已完成选品类目库 > 已删除批次”中恢复。已删除批次拒绝迟到的 Runner/SellerSprite 回传、命令、人工干预、外部派发状态及普通状态更新，轮询端会取消并跳过任何陈旧命令，恢复后才重新允许写入；归档事务与命令创建、派发更新、文件回传共用同一写锁，终态批次遗留的旧命令、Bridge 会话和外部派发也会在删除事务中一并收口。

未完成批次使用 `archive-request-v1.0.0` 的异步收尾接口：页面点击“停止并删除”后调用 `POST /api/batches/archive-request`，服务立即返回 `202` 和持久化请求 ID，不会让浏览器请求一直等待 Runner。请求先取消可取消的本地任务、普通浏览器命令和未送达的外部派发，再等待 Runner `done`/停止回执、Bridge 会话、本地租约和远程派发达到已知终态；状态会经过 `requested`、`cancelling`、`waiting`，只有全部阻断条件消失才调用原子归档。重复请求使用 `Idempotency-Key` 复用同一请求，`GET /api/batches/<batchId>/archive-request` 可查询状态；页面轮询和服务启动都会继续收口未完成请求。

收尾流程保持 fail-closed：仍存活或无法确认归属的遗留 PID、仍在线的 Bridge、已送达但未确认的外部任务派发，以及超过等待上限的请求不会被强杀或猜测归档，而是转为 `failed` 并显示具体原因，用户确认风险后可重新提交。迟到的普通心跳、ASIN 事件、JSON、命令回执和状态写入会被删除请求围栏拒绝；只接受当前会话的明确停止完成信号。新状态表为 `batch_archive_requests`，与批次 payload、严格筛选规则、Runner/Collector/Bridge 协议和 A-F 门禁分离。回滚可在启动前设置 `AMAZON_CONSOLE_CATEGORY_REPOSITORY_V1=0`，或恢复到部署前的 Git 提交；归档请求记录保留，不会物理删除批次数据。

类目导入先逐行预检：仓库未出现为绿色并默认导入；已有完成记录为红色且默认跳过，只有用户明确勾选才以独立 override 授权重导；同批重复、当前类目池已有或名称匹配不明确为黄色并阻止导入；格式错误或显式非 Amazon US 地址为灰色并阻止导入。导入项绑定原始行号和内容哈希，输入变化后旧选择失效；服务端在同一数据库临界区重新预检、授权并写入，避免并发状态变化绕过红色提示或产生同 node 的活动重复项。成功的红色 override 会逐项审计授权键、nodeIdPath、释放的完成条目 ID 和新条目 ID；失败的正式导入请求也保留拒绝审计。若请求处理中输入框已被改成下一批内容，旧请求完成后不会清空新内容，而会重新预检。

保守回滚可在启动前设置 `AMAZON_CONSOLE_CATEGORY_REPOSITORY_V1=0`。关闭后页面继续使用旧类目池导入契约，默认批次列表也不再应用独立归档视图；仓库表、审计记录和历史数据保留，不会被删除。该开关不改变 A-F、Runner、Collector、Bridge、历史去重或产物校验规则。

## 浏览器导出候选源

默认模式不需要 Open API 密钥。一次性安装 `http://127.0.0.1:8788/seller-sprite-bridge.user.js`、在 SellerSprite 产品研究页登录并粘贴控制台配对码后，创建批次即可自动开始。控制台会按批次类目和固定严格条件下发查询 URL；Bridge 只接受 US URL，兼容页面回写的 `minAmzUnit/maxAmzUnit` 销量字段，选中当前结果并等待导出记录完成，再把原始文件以带 SHA-256 的受控请求回传。每个类目必须最终有一份 24 小时内的 `.xlsx/.csv/.tsv` 导出；Bridge 或站点失败会进入 `needs_attention`，不会生成伪造候选。控制台只把这些文件当作候选来源；浏览器 Runner 结果仍不是最终 A-F 放行依据。

SellerSprite Bridge 的回滚方式是停用或删除 `sellersprite_browser_bridge_v1.user.js`，在候选任务行使用人工上传；服务端可通过 `AMAZON_CONSOLE_SELLERSPRITE_BRIDGE=0` 禁用自动下发，已有 A-F 门槛、历史台账和 Runner Bridge 不受影响。

## 卖家精灵 API（可选）

- 网关：`https://api.sellersprite.com`
- 认证请求头：`secret-key`
- 类目解析：`GET /v1/product/node`
- 选品查询：`POST /v1/product/research`
- 凭据：Windows DPAPI 加密文件 `C:\Users\13045\.codex\secrets\sellersprite-open-api.credential.xml`

控制台不会把 `secret-key` 写入批次、日志、前端或源代码。API 异常、类目歧义、来源证据缺失或严格预筛失败都会关闭失败，不会产生可确认队列。

## Browser Bridge v2

在 ScriptCat/Tampermonkey 中安装 `http://127.0.0.1:8788/browser-bridge.user.js`。首次安装后，在控制台点击“复制一次性配对码”，到 Amazon US 页面右下角的 Bridge 面板粘贴并配对。Bridge 会拒绝以下状态：

- Collector/Runner 面板不是各一个；
- 版本不是 `0.4.6.4/0.3.8.13`；
- Amazon 出现 CAPTCHA 或登录页；
- 配送地址没有显示要求的美国邮编。
- Runner 生成后的批次名、队列顺序或 8 位队列哈希与控制台当前任务不一致。

Bridge 协议 `2.1.3` / 脚本 `2.1.6` 会先重算控制台批准队列 SHA，再校验 Runner 严格历史成员、批次新鲜度、空结果状态及生成时间。队列、明确历史跳过清单、生成身份和执行来源会持久化为 `bridgeQueueContract/v1`，恢复、每次心跳和最终 JSON 回传都重新逐项验证。控制台的命令是“接管或启动 Runner”：若当前 Runner 已在同一批准队列上运行或已经完成，脚本只在完整契约和已保存结果前缀都匹配时，以 `adopted_existing` 明确记录接管，不会重新生成或重启；暂停中的批次不能作为新 Start 成功，必须使用“继续”。未知缺失、额外项、重排、重复、无效 ASIN、伪造历史命中或空待采集队列仍失败关闭。

每个 Bridge 会话同时绑定当前 32 位 Start 命令 ID、`generated_for_command` 或 `adopted_existing` 执行模式以及脚本版本。注册、心跳、事件和合并 JSON 的命令 ID 或执行来源任一不一致，服务端都会在持久化前拒绝。原始 Runner JSON 已回传后，页面禁用重复启动，服务端也拒绝再次重置该批次。设置 `ENABLE_RUNNING_BATCH_RECOVERY=false` 可禁用接管；设置 `ENABLE_RUNNER_HISTORY_SKIP_RECONCILIATION=false` 可回滚为完整队列精确相等。服务端同时校验协议号与脚本号，旧脚本不能领取启动命令；若回滚脚本版本，必须同步调整服务端批准版本。Runner 的 `done` 只表示等待 JSON 回传，只有契约一致的非空结果前缀通过原始合并 JSON 校验后才进入“可生成 Excel”。

启动命令按 Bridge 版本领取。`2.1.2` 或更早版本不会消耗待执行命令；更新到 `2.1.3` 后，配对状态和待执行命令会自动恢复。

旧版 Bridge 保留在 `http://127.0.0.1:8788/browser-bridge-v1.user.js`，仅用于回滚。

## 边界

- 卖家精灵 API 和 Runner 都只是证据与执行层，不能替代完整 A-F 最终验收。
- 主图下载失败会记录到报告；生成 Excel 后仍应检查图片嵌入数量和可读性。
- 自动流程不会处理 CAPTCHA、失效登录或配送地址选择，这些状态会进入“待确认”。

## 回滚

停止本机服务后重新安装 `browser_bridge_v1.user.js` 即可回退浏览器桥接；正式 Collector、Runner、A-F 规则和历史台账未被修改。

## 前端组件构建

控制台保留现有原生 HTML/CSS/JS 运行方式，并使用用户提供的 `@dangdang/ui` `0.2.5` 发布样式和组件类。按钮、状态徽标、进度条和提示条现在直接使用 `dd-button`、`dd-badge`、`dd-progress` 和 `dd-toast`；原有 ID、`data-action`、表单提交和轮询/SSE 事件不变。重新从固定压缩包生成并校验本地发布样式：

```powershell
cd C:\Users\13045\Documents\亚马逊电商选品
corepack pnpm --dir automation_console run build:ui
```

构建命令从 `vendor/dangdang-ui-0.2.5.tgz` 提取 `package/dist/styles.css`，SHA-256 不匹配时失败关闭。旧 `static/vendor/fluent-components.js` 不再由 `index.html` 加载，只保留为显式回滚资产；需要重建该资产时使用 `npm run build:fluent-rollback`。

### DangDang UI 0.2.5 兼容接入

`@dangdang/ui` `0.2.5` 已固定在 `vendor/dangdang-ui-0.2.5.tgz`，发布样式固定在 `static/vendor/dangdang-ui-0.2.5.css`，由 `static/dangdang-ui-adapter.css` 接入现有原生 HTML/JS 外壳。当前控制台不是 React 宿主，因此采用包内真实 CSS 组件类而不引入第二套 React 运行时；这既完成控件视觉更新，也避免整站重写影响当前批次。

适配默认通过 `body[data-ui-package="dangdang-ui-0.2.5"]` 开启，并使用紧凑密度：左栏固定在视口内独立滚动，类目池和批次列表各自保留内部滚动，完整条目仍可访问。版本、包哈希和回滚值记录在 `ui-package.json`。回滚时把 `static/index.html` 的 `data-ui-package` 改为 `legacy`，再移除两条 DangDang 样式链接即可；业务脚本和后端无需回退。

验证：

```powershell
npm run test:ui
```
