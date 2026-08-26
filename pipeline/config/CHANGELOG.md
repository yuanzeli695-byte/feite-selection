# config/CHANGELOG.md

规则文件改动记录。每次改动 rules.json / exclusions.json / pipeline.json 都在这里写一行。

## 2026-07-10 — 初始版本

- rules.json v1: 价格 9.9-50, 评分 ≥4.0, 评论 ≤100(+15 容差), 上架 ≤90 天, 变体 ≤25, 月销 50-300 理想/硬顶 1500
- rules.json v1: 流量硬门 latestPct ≥70 且 recent4Avg ≥70 且 recent4Min ≥70 且 weeksRead ≥3
- exclusions.json v1: 10 类硬排除品类,42 条 IP/角色关键词,12 条品牌 scrutiny
- pipeline.json v1: targetN=10, maxAttempts=100, SellerSprite cache TTL 168h, image cache 24h

## 2026-07-10 — 清理旧字段别名

- exclusions.json 只保留 `hardExclusions` / `reviewFlags` / `brandScrutiny`。
- 删除旧字段别名 `categories` / `ip_character_keywords` / `brand_scrutiny`,避免后续扩充词库时写到无效位置。

## 2026-07-10 — Batch2 接口清理

- pipeline.json 的 `candidateSources[*].ref` 改为 `runs/{runId}/...` 占位符,避免继续指向不存在或误导性的 `runs/new/...`。
- replay_existing_batch.py 对 `--candidates-json` 增加顶层数组校验,Claude/员工侧格式错误时直接报清晰错误。

## 2026-07-10 — 中文品名规则版落地

- 新增 config/zh_title_dict.json: 89 品类 + 57 修饰 + 25 语境 + 25 包装 + 20 保留品牌
- 新增 scripts/title_to_cn.py: 规则翻译引擎,支持单条/批量/regress 三种模式
- baseline 6 品 regress 覆盖 6/6,batch qualified_pool 5 品覆盖 5/5
- zh_title_overrides.json schema 不变,codex pipeline 层 0 改动
- 员工工作流 Step 3.5 加进 OPERATOR_CHECKLIST.md,--merge 保留手工覆盖
# 2026-07-31 aggregate natural traffic mode

- Added opt-in `rules_aggregate_natural_traffic.json`.
- Gate C uses `sum(naturalTraffic) / sum(totalTraffic) >= 70%` across at least three valid recent weeks.
- The original per-week/latest/average/minimum rule remains unchanged in `rules.json` for rollback.
