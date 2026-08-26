# SellerSprite F12 辅助抓取脚本 — 员工使用说明

**位置**: `scripts\sellersprite_console_extract.js`
**目标**: 员工在 SellerSprite 关键词页 F12 一键抓 20-40 个候选,拷贝 TSV 到 `candidate_meta_batch2.tsv`。

## Tier 1.1 查询硬过滤（SOP）

预设版本：`sellerSprite-query-hard-filter-v1`

在执行搜索/导出前，先在 SellerSprite 列表页设置以下**硬过滤**，不得放宽：

| SellerSprite 字段 | 查询端硬标准 |
|---|---:|
| 当前价格 | `$9.90-$50.00` |
| 评分 | `>=4.0` |
| 评论数 | `<=100` |
| 上架天数 | `<=90天` |
| 变体数 | `<=25` |
| 子体/月销量硬上限 | `<=1500` |

不同 SellerSprite 页面字段名称可能略有差异，使用语义对应的字段。某项在当前列表页没有过滤控件时，不得用近似区间代替；按原值导出，并由本地硬筛立即拒绝不合格项。

查询端不要把以下非硬指标变成放行或淘汰条件：

- 月销量理想区间：当前批准口径中 `50-300` 用于排序偏好，硬上限仍为 `1500`。
- 父体销量：不得冒充子体销量。
- BSR、卖家数、品牌集中度、关键词集中度、季节性和外观相似度：不是当前初筛硬门槛。
- 自然流量或广告代理字段：Tier 1.3 是否可用尚未确认，当前不得据此放行或淘汰。

护栏：查询端命中这些数值仍不能证明商品合格。导出后必须经过 `prepare_strict_candidate_pool.py` 的禁限售优先硬筛，并由 Runner 和验收层重新验证全部 A-F 门槛。

需要回退操作界面时可以清空 SellerSprite 列表过滤条件，但不得跳过后续本地硬筛；本地硬门槛不受影响。

## 用法(每个关键词重复一次)

1. **打开 SellerSprite**,登录状态 OK 的情况下,搜一个关键词(用 `keyword_seeds.md` 里的 70 个种子之一,比如 "picture frame")
2. **等结果全部加载**(下拉到底,让懒加载补完;或直接前 20-30 个也行)
3. **F12** 打开开发者工具,切到 **Console** 标签
4. **打开脚本文件**: `C:\Users\13045\Desktop\amazon_products\scripts\sellersprite_console_extract.js`,全选,复制
5. **粘贴到 Console 输入框**,回车执行
6. 看 Console 输出:
   - `found N candidate rows` — 找到 N 个行
   - `extracted M valid ASIN rows` — 成功提取 M 个 ASIN
   - `已复制 M 行 TSV 到剪贴板` — 成功
7. **打开** `runs\new_20260710_batch2\candidate_meta_batch2.tsv`(用记事本/Notepad++)
8. **删除**里面的示例行 `B0XXXXXXXX...`,保留第一行表头
9. **在表头下面粘贴**(Ctrl+V),保存

## 换下一个关键词

回到 SellerSprite,搜下一个种子,重复 F12 → 粘脚本 → 回车 → 追加粘到 TSV 末尾。

**推荐 4-6 个关键词就能凑 50-80 品**,每个关键词只挑前 15-25 个(不用全用完)。

## 常见问题

### Q1: `nothing extracted` / `found 0 candidate rows`

DOM 结构和脚本预期不一致。**处理**:
- 截图当前 SellerSprite 页面完整界面
- Console 里再跑一遍下面这段侦查代码,把输出截图:

```javascript
console.log('table tbody tr:', document.querySelectorAll('table tbody tr').length);
console.log('[data-asin]:', document.querySelectorAll('[data-asin]').length);
console.log('.product-card:', document.querySelectorAll('.product-card').length);
console.log('a[href*="/dp/"]:', document.querySelectorAll('a[href*="/dp/"]').length);
console.log('first row html snippet:', document.querySelector('table tbody tr, [data-asin], .product-card')?.outerHTML?.slice(0, 500));
```

- 把上面输出发给 Claude,让他做精准适配版

### Q2: 剪贴板复制失败

- 看 Console 输出的 `===COPY START===` 到 `===COPY END===` 之间的内容
- 手动复制那段(可能得点 Console 里的展开按钮)
- 粘到 TSV

### Q3: 抓到的某些字段是空的(比如 brand / launchDate / variations)

**正常**。脚本用通用选择器,SellerSprite 布局如果不匹配就抓不到。**员工手工补齐重要字段**:
- **必须补**: price / rating / launchDate / variations / image (这几个缺了 Codex 会 fail)
- **可选补**: brand / childSales / parentSales (Codex 缺了不阻断)

补的时候直接编辑 TSV,一列一列填就行。

### Q4: 抓到了不符合查询端硬标准的品

先检查 SellerSprite 的 `sellerSprite-query-hard-filter-v1` 是否仍生效。不符合任一硬标准的行不得进入候选队列；若平台过滤漏出，保留原始值进入本地审计后由 `prepare_strict_candidate_pool.py` 拒绝，不能手工改值使其通过。

### Q5: 不知道 F12 是啥

- F12 = 键盘上从左数第 12 个功能键
- Windows Chrome 里按 F12 → 弹出开发者工具 → 顶部有 "Elements / Console / Sources ..." 标签,点 **Console**
- 底部有输入框,粘代码就行

## 抓完后

回到 `runs\new_20260710_batch2\OPERATOR_CHECKLIST.md`,按 Step 3 开始跑 candidate_tsv_to_json.py。

随后必须运行 `prepare_strict_candidate_pool.py` 做精确硬筛。`candidate_tsv_to_json.py` 只负责字段标准化和历史排重，不负责证明候选通过商业门槛。

## 已知局限

- 这是**通用+保守版**脚本,准确率 60-80%。SellerSprite 改版后可能失效
- 遇到失败提交侦查数据给 Claude,做**精准适配版 v2**
