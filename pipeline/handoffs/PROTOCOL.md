# Claude ↔ Codex Handoff 协议 v1

**目的**: 让 Codex/Claude 每次工作开始时**自动扫一遍未读对接报告**,不再依赖用户手工转发。

**位置**: `C:\Users\13045\Desktop\amazon_products\handoffs\`

---

## 1. 目录结构

```
handoffs/
├── PROTOCOL.md              本文件,双方启动前必读
├── inbox_for_codex/         Claude 给 Codex 的待处理报告
├── inbox_for_claude/        Codex 给 Claude 的待处理报告
└── archive/                 双方处理完的历史报告(按年月分)
    └── 2026-07/
```

## 2. 文件命名规约(强制)

```
YYYYMMDD_HHMM_<from>_to_<to>_<slug>.md
```

- `YYYYMMDD_HHMM`: 生成时的本地时间(排序用)
- `<from>` / `<to>`: `claude` 或 `codex`
- `<slug>`: 3-6 词英文短语,`_` 分隔,能一眼看出主题

**例子**:
```
20260710_1535_claude_to_codex_zh_title_rule.md
20260710_1122_codex_to_claude_batch2_cleanup.md
20260711_0930_claude_to_codex_batch3_seeds.md
```

命名不合规 = 对方可以直接忽略并归档到 `archive/malformed/`。

## 3. 报告开头 5 行 metadata(强制)

每份报告第 1-5 行必须是 YAML frontmatter,给对方脚本快速扫描用:

```markdown
---
from: claude          # claude | codex
to: codex             # claude | codex
priority: p1          # p0 (阻断当前 batch) | p1 (影响下一批) | p2 (长期)
requires_action: yes  # yes = 对方要做事; no = 只是同步信息
tags: [zh_title, batch2, rules_config]
---

# 报告标题

正文...
```

**5 行都得有**,否则对方可能跳过。

## 4. 启动时的扫描流程(自动化建议)

Codex 每次接到用户新任务时,建议执行:

```powershell
$INBOX = "C:\Users\13045\Desktop\amazon_products\handoffs\inbox_for_codex"
Get-ChildItem $INBOX -Filter "*.md" | Sort-Object Name | ForEach-Object {
    $head = Get-Content $_.FullName -Head 5
    # 解析 frontmatter,按 priority 排序展示
    Write-Host "PENDING: $($_.Name)"
    Write-Host $head
}
```

Claude 侧同理,扫 `inbox_for_claude/`。

**用户交互层面**: 用户没必要每次说"看一下 codex 给你的报告",双方启动前默认扫一遍 inbox 就行。

## 5. 处理完成后的动作

处理完一份报告,**必须**:

1. 把该 md 从 `inbox_for_<self>/` **移动**到 `archive/YYYY-MM/`
2. 如果需要回信,在 `inbox_for_<other>/` 新建一份带 frontmatter 的回执 md
3. 回执文件名的 slug 建议以 `_reply_to_<原 slug>` 结尾便于溯源

**例子**:
```
Codex 处理完:  20260710_1535_claude_to_codex_zh_title_rule.md
   → mv 到:   archive/2026-07/20260710_1535_claude_to_codex_zh_title_rule.md
   → 回执:    inbox_for_claude/20260710_1600_codex_to_claude_reply_to_zh_title_rule.md
```

## 6. 优先级语义

| 级别 | 意思 | 建议响应时间 |
|---|---|---|
| **p0** | 阻断当前批次上线/发现严重 bug | 立刻处理,其他事情让路 |
| **p1** | 影响下一批效率/维护 debt 累积 | 当前手头事情做完就上 |
| **p2** | 长期改进/规模化准备 | 有空闲再处理,可能一直不做 |

## 7. requires_action 的用法

- `yes` — 对方看完必须做事(改代码/回执/落地方案)
- `no` — 只是通报进展/结果同步,对方看完可以直接归档

## 8. 索引维护(可选,人看的)

如果 inbox 里超过 3 份报告没处理,建议**双方在 `handoffs/INBOX.md`** 里加一行索引,便于用户扫一眼看谁欠谁:

```markdown
# Handoff INBOX 状态

## Codex 未处理
- 20260710_1535_claude_to_codex_zh_title_rule.md  [p1, no action]

## Claude 未处理
- 20260711_0900_codex_to_claude_batch3_review.md  [p1, requires reply]
```

## 9. 不要做的事

- ❌ 不要在报告里 @人名或群名 — 这只在双方之间流转
- ❌ 不要用 png/xlsx/word 交付关键决策信息 — 决策必须 md 纯文本
- ❌ 不要修改对方已经归档的 md — 有更新写新的
- ❌ 不要跳过 frontmatter — 对方脚本扫不到就没了
- ❌ 不要放二进制附件在 handoffs/ 下 — 用其他目录 + md 里链接

## 10. 迁移路径(存量文件)

存量 6 份 CLAUDE_*.md 在 amazon_products 根目录,**保留原位不删**(其他脚本可能引用),但**同时**在 archive/ 里放一份 symlink 或 copy,方便统一检索。**新报告一律进 inbox_for_*/**。

## 11. 何时启用

**即刻**。Claude 从下一份报告开始按本协议命名 + 加 frontmatter + 放进 inbox_for_codex/。Codex 收到本协议后:

- 阅读 → 认可 → 回执到 inbox_for_claude/(带 frontmatter,slug: `reply_to_handoff_protocol_v1`)
- 之后每次启动前扫 inbox_for_codex/

如果 Codex 有异议(比如觉得目录结构不对、frontmatter 字段要加),把修订建议写在回执里,不要沉默地不遵循 —— 那样双方会协议漂移。
