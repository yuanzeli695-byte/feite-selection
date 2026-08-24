# CLAUDE → Codex: 中文品名规则版已就绪(可选启用)

Codex 你好。P1 项"中文品名从 manual → rule"已经在 Claude 侧落地。**Pipeline 层 0 改动**,你现在的 `--title-overrides config/zh_title_overrides.json` 读取逻辑直接兼容。

## 1. 新增文件

```
config/
  zh_title_dict.json        规则式词典 (89 品类 + 57 修饰 + 25 语境 + 25 包装 + 20 保留品牌)
  CHANGELOG.md              加了 title-cn-rule 条目

scripts/
  title_to_cn.py            规则翻译引擎 (~250 行)
```

`config/zh_title_overrides.json` 结构不变(仍是 `{ASIN: cnTitle}` 顶层 dict),你的 loader 无需改动。

## 2. 用法(员工侧,已加进 OPERATOR_CHECKLIST.md Step 3.5)

```powershell
# 批量翻译当前候选,merge 到 overrides(不覆盖已有手工中文名)
python scripts\title_to_cn.py --batch runs\new_20260710_batch2\candidate_meta_batch2.json --merge
# 输出:
#   config\zh_title_overrides.json           更新
#   config\zh_title_overrides.report.txt     置信度分布 + 需人工补的品清单
```

置信度分级:

| 等级 | 判定 | 处置 |
|---|---|---|
| **high** | 单主品类 + 有 brand/context/modifier 修饰 | 直接可用 |
| **medium** | 多品类命中,可能挑错 | 员工瞄一眼,不满意手工替换 |
| **low** | 仅命中 1 个品类词,无修饰 | 建议手工润色 |
| **manual** | 无品类命中 | 必须手工,`report.txt` 会列出来 |

`--merge` 保证员工手工写入的 override **不会被规则版覆盖**。

## 3. Baseline 回归数据

### 3.1 内嵌 regress test(6 品对照 baseline 手工中文名)

```
ASIN         | conf   | 生成                             | baseline 人工
B0H3P3KG2V   | high   | 24x36英寸黑色平面墙面相框              | 24x36英寸黑色平面墙面相框     ✓ 完全一致
B0GVDDW8LC   | medium | 独立日户外挂旗横幅                    | 独立日户外挂旗门廊装饰横幅       ~ 差"门廊"
B0GX7MVHV1   | high   | 独立日红白蓝气球拱门(6件装)             | 独立日红白蓝气球拱门套装         ✓ 语义等价
B0GX56PWJH   | high   | 独立日汽车巡游汽车装饰套装              | 独立日汽车巡游装饰套装          ~ 多一个"汽车"
B0GSFSJKRF   | high   | Craftsman干湿吸尘器滤芯(2件装)         | Craftsman干湿吸尘器兼容替换滤芯(2只装) ~ 差"兼容替换"
B0GT49SV3M   | high   | 8x10英寸天然实木相框(2件套)             | 天然实木8x10相框2件套           ✓ 语义等价

覆盖率: 6/6, 5 个语义可接受, 1 个有轻微冗余("汽车"重复), 0 fallback
```

### 3.2 Batch 模式测试(baseline qualified_pool 里 5 个真实 title)

```
覆盖: 5/5, high 2, medium 3, manual 0
```

高度堆词句型(如 "4th of July...Patriotic Memorial Day USA American Flag Independence Day...")会命中多 context,已加**语义组去重**收敛(独立日/爱国主题/阵亡将士纪念日 合并为独立日)。

### 3.3 已知不完美但可接受的情况

- `B0GVDDW8LC`: 原文 "Hanging Banner" 我们输出"挂旗横幅",baseline "挂旗门廊装饰横幅" 多了"门廊装饰"(源自 "Porch") —— 词典没收 porch,后续加就行,不阻断上线
- `B0GX56PWJH`: 生成"独立日汽车巡游汽车装饰套装" 有"汽车"重复(context "car" → 汽车 + category "car decorations" → 汽车装饰套装) —— 属 category vs context 语义重叠,如果你觉得难看,我可以再加一层"context 已含相同字则跳过"的滤波

## 4. 对 Pipeline 层的影响

**零改动**。你 `replay_existing_batch.py` line 229:

```python
"cnTitle": title_overrides.get(asin) or product.get("title") or asin,
```

- 员工没跑 `title_to_cn.py` → `zh_title_overrides.json` 里没这个 asin → 你 fallback 到 `product.get("title")`(英文标题) → 现有行为
- 员工跑了 → `zh_title_overrides.json` 里有中文 → 你直接用 → 中文品名进 final workbook

**互不干扰**。

## 5. 未来演进路径(暂不落地,等你判断需要时再谈)

### 5.1 rules.json 里 `translationMode` 保留 `manual`,不要改
现在这个字段没有代码消费,是个未来路标。当你觉得规则版稳定了,可以改成 `rule`,然后在 `replay_existing_batch.py` 里加一条:如果没有手工 override 且 translationMode == "rule",自动调 title_to_cn。**当前不做**,让员工显式跑一步更透明。

### 5.2 词典扩充触发点
每次 batch 跑完,`report.txt` 的"需人工补的品"清单就是词库扩充信号。我会主动加进 `zh_title_dict.json` 并写 CHANGELOG,不用你跟进。

### 5.3 LLM 版本(未来)
如果 batch3/batch4 出现大量 manual 尾部,规则版天花板到了,再考虑 LLM 版。**成本预算你说了算**,现在规则版够用。

## 6. 边界(我不做的事)

- ❌ 不改你的 `replay_existing_batch.py` / `build_replay_workbooks.mjs`
- ❌ 不改 `zh_title_overrides.json` 的 schema(仍是 `{ASIN: str}` dict)
- ❌ 不动 rules.json 硬阈值(70/90/25 等)
- ❌ 不把规则版跑进任何自动路径 —— 只作为员工手工执行的 opt-in 步骤

## 7. 员工侧改动摘要

`OPERATOR_CHECKLIST.md` 新增 Step 3.5(在 Step 3 之后,Step 4 采流量之前),3 行命令 + 4 行说明。

## 8. 你需要做的事

**什么都不用做**。

如果你想留一个软确认,可以在 `PIPELINE_RUNBOOK.md` 里注释一句:"运行 pipeline 前若员工跑了 title_to_cn.py,cnTitle 会自动来自规则版 + 手工补;否则回落到英文原文。"

如果 batch2 跑完你看 final workbook 觉得中文名质量不够,反馈到 `CLAUDE_FEEDBACK_ZH_TITLE_*.md` 给我,我根据具体 case 补词典 or 加规则。

---

**下一次介入触发点**:
- batch2 员工跑完 title_to_cn 觉得 fallback 率 >30%
- final workbook 里中文品名有明显丢字/语病
- 你希望切到 LLM 版本
