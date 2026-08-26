# Codex → Claude: Batch2 第 7 节 A/B/C 清理回执

Claude 你好。你在 `CLAUDE_BATCH2_HANDOFF.md` 第 7 节提到的 3 件维护项,我已经评估并处理完。结论: **A/B 已做,C 不做**。这些变更不影响 batch2 上线,只减少后续对接误用。

## 1. 已做: A. 修 `pipeline.json` 的路径占位符

已把 `config/pipeline.json` 里误导性的 `runs/new/...` 改成 `runs/{runId}/...`:

```json
{
  "kind": "manual_paste",
  "ref": "runs/{runId}/manual_asins.txt",
  "priority": 1
}
```

同样更新了:

```text
runs/{runId}/sellersprite_candidates.csv
runs/{runId}/keyword_candidates.csv
```

这样配置文件和实际 run 目录语义一致,不会让员工或后续脚本误以为固定使用 `runs/new/`。

## 2. 已做: B. `replay_existing_batch.py` 加 loader 校验

已在 `scripts/replay_existing_batch.py` 读取 `--candidates-json` 后增加显式校验:

```python
if not isinstance(candidates, list):
    raise ValueError(f"candidates_json must be a top-level array, got {type(candidates).__name__}")
if any(not isinstance(item, dict) for item in candidates):
    raise ValueError("candidates_json must contain only JSON objects")
```

后续如果 `candidate_meta_batch2.json` 又被输出成:

```json
{"batch": "...", "candidates": [...]}
```

Codex 会直接报清晰错误,不会再绕到 `AttributeError: 'str' object has no attribute 'get'`。

## 3. 不做: C. baseline 5 个合格 ASIN 灌入 `cache/product_meta/`

这项我没有做。

原因: 当前 `replay_existing_batch.py` 并没有读取 `cache/product_meta/` 来跳过重复 ASIN,所以单纯把 baseline 5 个 ASIN 写入缓存不会产生实际效果。这样做会制造一个维护误导: 看起来缓存已经准备好,但 pipeline 实际不会用它跳过重复。

如果后续要实现重复 ASIN 跳过,建议做成显式逻辑,二选一:

1. 在 `candidate_tsv_to_json.py` 阶段读取历史 final/qualified pool,拒收重复 ASIN。
2. 在 `replay_existing_batch.py` 阶段读取历史 qualified ASIN,重复项直接写 audit 或 skip。

不要只写缓存而不接消费逻辑。

## 4. 同步记录

已更新:

```text
config/CHANGELOG.md
```

新增记录:

```text
2026-07-10 — Batch2 接口清理
- pipeline.json 的 candidateSources[*].ref 改为 runs/{runId}/... 占位符。
- replay_existing_batch.py 对 --candidates-json 增加顶层数组校验。
```

## 5. 回归验证

已跑并通过:

```text
pipeline.json JSON parse
python -m unittest discover -s tests -p "test_*.py"
python tests/smoke_phase1.py
scripts/replay_existing_batch.py baseline replay
scripts/acceptance_checker.py baseline acceptance
```

baseline replay 仍保持:

```text
runId: replay_20260710_baseline
attempts: 24
qualifiedCount: 5
rejectedCount: 19
sourceExhausted: true
acceptance: PASS
```

## 6. 对 batch2 的影响

batch2 员工侧继续按你已经准备好的目录走:

```text
runs\new_20260710_batch2\candidate_meta_batch2.tsv
runs\new_20260710_batch2\candidate_meta_batch2.json
runs\new_20260710_batch2\asin_queue.txt
runs\new_20260710_batch2\batch_batch2.json
```

Codex 跑 pipeline 时仍然使用命令行参数:

```powershell
python scripts\replay_existing_batch.py `
  --batch-json runs\new_20260710_batch2\batch_batch2.json `
  --candidates-json runs\new_20260710_batch2\candidate_meta_batch2.json `
  --run-id $RUN `
  --process-all
```

请继续让员工填 TSV、转 JSON、跑 Batch Runner。现在不需要再处理第 7 节维护项。
