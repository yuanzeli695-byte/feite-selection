---
from: claude
to: codex
priority: p1
requires_action: yes
tags: [handoff_protocol, workflow, session_startup]
---

# 建立双向 handoff 协议,请从下次启动开始扫 inbox

Codex,用户希望我们停止依赖手工"看一下对方给你的报告",改为**双方每次启动时自动扫 handoffs/inbox_for_<self>/**。

## 已完成

- 建了 `handoffs/PROTOCOL.md`(v1),定义了命名规约、frontmatter、优先级、处理流程
- 建了 `handoffs/inbox_for_codex/` 和 `handoffs/inbox_for_claude/`
- 建了 `handoffs/archive/`

## 请 Codex 做的事

### 1. 阅读 `handoffs/PROTOCOL.md`

如果对目录布局/frontmatter 字段/优先级定义有异议,写回执告诉我,我们协商 v2。

### 2. 修改你的启动流程

每次接到用户新任务时,先扫 `handoffs/inbox_for_codex/`:

```powershell
Get-ChildItem "C:\Users\13045\Desktop\amazon_products\handoffs\inbox_for_codex" -Filter *.md |
    Sort-Object Name |
    ForEach-Object {
        Write-Host "==== $($_.Name) ===="
        Get-Content $_.FullName -Head 6
    }
```

按 priority(p0 → p1 → p2)顺序处理,处理完后:
- 把 md 从 inbox 移到 `handoffs/archive/2026-07/`
- 如需回执,新建一份 md 放到 `handoffs/inbox_for_claude/`

### 3. 回执本报告(确认协议)

回执到 `handoffs/inbox_for_claude/`,文件名建议:

```
YYYYMMDD_HHMM_codex_to_claude_reply_to_handoff_protocol_v1.md
```

frontmatter 里 `requires_action: no`(纯确认),tags 加 `handoff_protocol`。

## 存量迁移问题

根目录还有 6 份 `CLAUDE_*.md`(INTEGRATION / REPLY_NEXT_CANDIDATE_POOL / BATCH2_HANDOFF / BATCH2_CLEANUP_REPORT / TO_CODEX_DEDUPE_LANDED / TO_CODEX_ZH_TITLE_RULE)。

**处理建议**:
- 根目录**保留原文件**不动 — 你的 CLAUDE_INTEGRATION.md 可能被其他脚本/文档引用,别造成 broken link
- 把它们**复制**一份到 `handoffs/archive/2026-07/`,统一检索用
- 从**本报告开始**,新报告一律走 `handoffs/inbox_*` 目录

如果你觉得这个策略不合适,回执里说,我们改。

## 对 pipeline 层的影响

**零**。这是双方 session 启动流程的改动,不涉及 pipeline / config / scripts。

## 优先级说明

标 p1 是因为:
- 不阻断 batch2(batch2 继续按现流程走)
- 但影响未来所有 handoff 效率,越早统一越好
- 用户不希望再手工转发对接报告

## 边界

- ❌ 不改 pipeline 4 大件
- ❌ 不改 config/*.json
- ❌ 不动员工工作流(EMPLOYEE_GUIDE / OPERATOR_CHECKLIST)

## 下一步

- 你回执 → 我确认 → 之后所有新报告走 handoffs/inbox_*
- 你不同意某些细节 → 我改 PROTOCOL v2 → 再来一轮

如果 3 小时内没看到你回执,我默认你还没扫到本报告 — 会主动在下一次用户交互时提醒。
