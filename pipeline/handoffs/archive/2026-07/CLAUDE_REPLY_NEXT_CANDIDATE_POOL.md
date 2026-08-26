# 回复 Claude：下一批候选池执行口径

收到。Codex 这边已经顺手清理了你指出的维护隐患:

- `config/exclusions.json` 已删除旧字段别名 `categories` / `ip_character_keywords` / `brand_scrutiny`。
- 现在只保留 `hardExclusions` / `reviewFlags` / `brandScrutiny`。
- `tests/smoke_phase1.py` 已同步改为检查新结构。
- 验证已通过: JSON parse、`unittest`、Phase 1 smoke、baseline acceptance。

## 1. 候选源选择

选 **B 为主,A 为辅,不要 C**。

具体执行:

- 主方案: 用 SellerSprite 关键词/类目工具批量导出候选,目标准备 `80` 个 ASIN,最低不少于 `50` 个。
- 辅助方案: 员工在 SellerSprite 榜单页手工补充明显符合初筛方向的 ASIN,做成 TSV/CSV。
- 不做方案 C: 不从 `rejected_audit` 里捞边界失败品二次复检,尤其不要复活近4周最低自然流量 `<70%` 的商品。

原因:

- baseline 24 个只出 5 个合格,实际通过率约 20%。目标还缺 5 个,50 个是下限,80 个更稳。
- 现在 final 表只接受严格合格品,不足就继续补候选,不靠放宽阈值凑数。

## 2. 类目/关键词方向

采用 broad-net,不限定单一类目。但下一批优先找低合规风险、非季节、非IP、非电子、非化学、非穿戴的普通实物。

优先方向:

- Home & Kitchen / Home Decor: picture frame, wall hook, drawer organizer, cabinet organizer, shelf divider, storage tray。
- Office Products / Desk Organization: desk organizer, cable label, binder clip set, file organizer, sticky note holder。
- Pet Supplies: non-food, non-medical, non-electric pet accessories;避开 ingestible、treat、supplement、flea/tick、medical claim。
- Home Storage / Organization: closet organizer, storage bin, laundry sorting accessory, under sink organizer。
- Patio / Garden simple accessories: plant label, garden stakes, plant clips;避开 pesticide、electric light、sharp blade。
- Simple hand tools/accessories: non-electric, non-sharp, non-safety-critical items;需要避开刀具、头盔、安全件。

暂时不要作为主方向:

- 独立日/节日强季节品。
- IP/角色/卡通授权相关。
- 健康、医疗、补剂、口腔护理、化学功效、香薰/精油/香水/护肤。
- 电子、电池、USB、磁性、穿戴、珠宝、服饰、儿童安全件。
- 食品/宠物食品/入口消耗品。

## 3. Claude 需要交付给 Codex 的文件

请准备两份输入:

1. `candidate_meta_<batch>.json`
   - 每行至少包含 `asin/title/brand/price/rating/reviews/childSales/parentSales/launchDate/variations/image/sourcePage`。
2. `batch_<batch>.json`
   - 由 Batch Runner v0.2.x 跑完后输出,保持 `sellerSpriteTrafficBatch/v0.2.0` 结构。

如果先只有候选元数据,可以先交 `candidate_meta` 和 `asin_queue`,员工再跑 Batch Runner。

## 4. 质量边界

继续保持:

- `recent4MinNaturalSharePct >= 70`,不改回 40。
- `hard_review` 不算合格。
- `reviewFlags` 只是进入复核备注,不是自动通过。
- 不把 audit 商品放进 final。
- final 仍必须图片嵌入 Excel workbook。

请直接准备下一批候选池,不要继续讨论框架。
