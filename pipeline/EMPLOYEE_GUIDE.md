# SellerSprite 流量采集工具 员工使用指南

## 三个脚本的分工(先看这个)

| 脚本 | 用途 | 输入 | 何时用 |
|---|---|---|---|
| Traffic Collector 0.4.x | 单品流量采集 | 当前打开的 Amazon 商品页 | 手动看单个 ASIN 的自然流量 |
| Batch Runner Generic 0.2.x | 按输入队列批量采集 | 自己粘贴的 ASIN 列表 | 已有一批 ASIN,想批量拿流量数据 |
| ~~Batch Runner 20 (0.1.x)~~ | 已弃用 | 硬编码 20 个 ASIN | **不要装,不要用** |
| Product Discovery | 找新品 | 关键词/品类 | **暂未开发**,请手工在 SellerSprite 榜单页找新 ASIN |

## 日常工作流

### Step 1 - 找新品(手工)
在 SellerSprite 榜单/搜索页,按公司选品规则挑候选 ASIN,整理成一行一个 ASIN 的文本,或 CSV(表头 `asin`,可选 `titleHint`, `note`)。

### Step 2 - 跑流量(Batch Runner Generic)
1. 打开任意 Amazon 商品页(不用是候选之一)
2. 点右下角 Batch Runner 面板
3. 在 Queue 文本框粘贴 ASIN 列表
4. 填 Operator(你的名字/工号),Batch name 可选
5. 点 **Generate batch** → 会显示 queueHash 前 8 位,确认无误
6. 点 **Start** → 逐个跳转采集,不要碰浏览器,等它跑完
7. 完成后 **Copy JSON** → 保存到 `batch_<你的名字>_<queueHash 前8>.json` → 发给数据组

### Step 3 - 别做的事
- 不要期待 Batch Runner 帮你"找新品",它只跑你输入的队列
- 不要一边跑一边开 Chrome 翻译(会污染 JSON 输出)
- 不要多个员工用同一浏览器 profile 跑不同批次(localStorage 会串)
- 卡住时不要点刷新,先看面板左下角 log;Status 一直不变 60+ 秒才算真卡

## 面板按钮

| 按钮 | 作用 |
|---|---|
| Generate batch | 输入队列后生成本批次 hash 和元数据 |
| Start / Resume | 开始跑;跑一半停了续跑也点这个 |
| Pause | 手工暂停 |
| Copy JSON | 跑完复制结果 → 存文件 → 发数据组 |
| Clear | 只清本批次结果,其他 queueHash 批次不动 |
| 下拉框 | 切换到另一个已保存批次 |

## 故障速查

| 现象 | 处理 |
|---|---|
| Status 卡在 waiting-collector 超过 60 秒 | 关翻译,刷新页面,面板会自动 resume |
| 循环刷新同一 ASIN | Amazon 变体重定向;Batch Runner 会自动熔断跳过 |
| 某行 status: error / page_not_found | 商品可能下架,跳过让数据组人工复核 |
| Copy JSON 是空的 | 检查 Chrome 有没有翻译整页,关了再 Copy |

## 交付格式

跑完的 JSON 发到群里,标题: `[流量] <你的名字> <日期> <ASIN 数量>`
例: `[流量] Sarah 2026-07-10 25个`

## 数据组现在怎么用 JSON

你交付的 JSON 不再直接混进最终主表。数据组会先跑 pipeline:

1. 先按禁限售/IP/健康化学/价格/评分/上架天数等硬规则过滤。
2. 再判断自然流量:最新、近4周均值、近4周最低都要达到 70% 以上。
3. 只有 `QUALIFIED` 状态的 ASIN 才会进入 `final_candidates.xlsx`。
4. 被剔除的 ASIN 会进入 `rejected_audit.xlsx`,用于回查原因。

如果最终合格数不足目标数量,不是把剔除品补进 final 表,而是继续准备下一批 ASIN 让 Batch Runner 跑流量。
