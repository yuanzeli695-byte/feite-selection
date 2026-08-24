(function initializeCategoryRepositoryUI(root) {
  "use strict";

  const PREVIEW_STATUS = Object.freeze({
    ready: Object.freeze({
      tone: "green",
      label: "仓库未出现",
      detail: "默认导入",
      selectable: true,
      selectedByDefault: true,
    }),
    screened: Object.freeze({
      tone: "red",
      label: "已有完成筛选记录",
      detail: "默认不导入；勾选表示明确仍然导入",
      selectable: true,
      selectedByDefault: false,
    }),
    ambiguous: Object.freeze({
      tone: "yellow",
      label: "名称匹配不明确",
      detail: "请补全 nodeIdPath 后重新预检",
      selectable: false,
      selectedByDefault: false,
    }),
    duplicate: Object.freeze({
      tone: "yellow",
      label: "本次导入重复",
      detail: "保留首次出现的条目",
      selectable: false,
      selectedByDefault: false,
    }),
    in_pool: Object.freeze({
      tone: "yellow",
      label: "当前类目池已有",
      detail: "无需重复导入",
      selectable: false,
      selectedByDefault: false,
    }),
    invalid: Object.freeze({
      tone: "gray",
      label: "格式错误",
      detail: "此行不可导入",
      selectable: false,
      selectedByDefault: false,
    }),
  });

  const REPOSITORY_SCOPE_LABEL = "Runner 已筛选，未做 A-F 最终验收";

  function previewMeta(status) {
    return PREVIEW_STATUS[String(status || "")] || PREVIEW_STATUS.invalid;
  }

  function itemDetail(item) {
    const status = String(item?.status || "invalid");
    const meta = previewMeta(status);
    if (status === "invalid") return String(item?.error || item?.message || item?.reason || meta.detail);
    if (status === "duplicate" && item?.duplicateOf) {
      const duplicateLine = /^line:(\d+)(?::|$)/.exec(String(item.duplicateOf));
      return duplicateLine ? `与第 ${duplicateLine[1]} 行重复` : meta.detail;
    }
    if (status === "screened") {
      const count = (Array.isArray(item?.matches) ? item.matches : []).reduce(
        (total, match) => total + Math.max(0, Number(match?.completionCount || 0)),
        0,
      );
      return count > 0 ? `仓库已有 ${count} 次完成筛选；勾选表示明确仍然导入` : meta.detail;
    }
    if (status === "ambiguous") {
      const count = Array.isArray(item?.matches) ? item.matches.length : 0;
      return count > 1 ? `名称匹配 ${count} 个历史 nodeIdPath，请补全后重试` : meta.detail;
    }
    return String(item?.message || item?.reason || meta.detail);
  }

  function normalizePreview(payload) {
    const rawItems = Array.isArray(payload?.items) ? payload.items : [];
    const items = rawItems.map((rawItem, index) => {
      const status = Object.hasOwn(PREVIEW_STATUS, String(rawItem?.status || ""))
        ? String(rawItem.status)
        : "invalid";
      const meta = previewMeta(status);
      const key = typeof rawItem?.key === "string" ? rawItem.key : "";
      return {
        ...rawItem,
        key,
        line: Number(rawItem?.line || index + 1),
        status,
        tone: meta.tone,
        statusLabel: meta.label,
        statusDetail: itemDetail({ ...rawItem, status }),
        selectable: meta.selectable && Boolean(key),
        selectedByDefault: meta.selectedByDefault && Boolean(key),
      };
    });
    return {
      schemaVersion: String(payload?.schemaVersion || ""),
      featureVersion: String(payload?.featureVersion || ""),
      marketplace: String(payload?.marketplace || "Amazon US"),
      scope: String(payload?.scope || ""),
      counts: payload?.counts && typeof payload.counts === "object" ? { ...payload.counts } : {},
      items,
      selectedKeys: items.filter((item) => item.selectedByDefault).map((item) => item.key),
    };
  }

  function buildImportSelection(items, selectedKeys) {
    const selected = selectedKeys instanceof Set ? selectedKeys : new Set(selectedKeys || []);
    const selectedItems = (Array.isArray(items) ? items : []).filter(
      (item) => item.selectable && selected.has(item.key),
    );
    return {
      selectedKeys: selectedItems.map((item) => item.key),
      overrideScreenedKeys: selectedItems
        .filter((item) => item.status === "screened")
        .map((item) => item.key),
    };
  }

  function flattenRepository(payload) {
    const rows = [];
    for (const category of Array.isArray(payload?.items) ? payload.items : []) {
      for (const completion of Array.isArray(category?.completions) ? category.completions : []) {
        const batchId = String(completion?.batchId || "");
        const scope = String(category?.scope || payload?.scope || "");
        rows.push({
          key: `${String(category?.key || category?.nodeIdPath || "category")}|${batchId}`,
          categoryKey: String(category?.key || ""),
          marketplace: String(category?.marketplace || payload?.marketplace || "Amazon US"),
          nodeIdPath: String(category?.nodeIdPath || ""),
          displayName: String(completion?.displayName || category?.displayName || category?.nodeIdPath || "-"),
          batchId,
          batchName: String(completion?.batchName || batchId || "-"),
          completedAt: String(completion?.completedAt || category?.lastCompletedAt || ""),
          archived: Boolean(completion?.archived),
          archivedAt: String(completion?.archivedAt || ""),
          scope,
          scopeLabel: scope === "console_completed_runner_unaccepted" ? REPOSITORY_SCOPE_LABEL : "口径未知",
          completionCount: Math.max(0, Number(category?.completionCount || 0)),
        });
      }
    }
    return rows.sort((left, right) => {
      const byTime = Date.parse(right.completedAt) - Date.parse(left.completedAt);
      if (Number.isFinite(byTime) && byTime !== 0) return byTime;
      return right.completedAt.localeCompare(left.completedAt) || left.batchName.localeCompare(right.batchName);
    });
  }

  function importResultSummary(result) {
    const added = Math.max(0, Number(result?.addedCount || 0));
    const selected = Math.max(0, Number(result?.selectedCount ?? added));
    const outcomes = Array.isArray(result?.outcomes) ? result.outcomes : [];
    const outcomeSkipped = outcomes.filter((item) => !["added", "created", "imported", "success"].includes(String(item?.outcome || item?.status || "").toLowerCase())).length;
    const skipped = Math.max(0, Number.isFinite(Number(result?.skippedCount))
      ? Number(result.skippedCount)
      : outcomes.length
        ? outcomeSkipped
        : selected - added);
    const text = skipped > 0
      ? `已导入 ${added} 个类目，另有 ${skipped} 行未导入`
      : `已导入 ${added} 个类目`;
    return { added, selected, skipped, text, tone: skipped > 0 ? "warn" : "good" };
  }

  function shouldClearSubmittedInput(currentValue, submittedValue) {
    return String(currentValue ?? "") === String(submittedValue ?? "");
  }

  function batchArchiveEligibility(batch) {
    const request = batch?.archiveRequest;
    const requestStatus = String(request?.status || "");
    const requestStates = new Set(["requested", "cancelling", "waiting"]);
    if (requestStates.has(requestStatus)) {
      const phase = String(request?.phase || requestStatus);
      const phaseLabels = {
        requested: "已提交停止请求",
        cancelling: "正在停止任务",
        waiting: "等待任务收尾",
      };
      return {
        eligible: false,
        reason: String(request?.lastError || phaseLabels[phase] || "正在删除收尾"),
        mode: "pending",
        requestStatus,
      };
    }
    if (requestStatus === "failed") {
      return {
        eligible: batch?.archiveRequestEligible === true,
        reason: String(request?.lastError || "上次删除请求未完成，可重新提交"),
        mode: "request",
        requestStatus,
      };
    }
    // Keep the original shape for immediate archive/blocked states; mode is
    // only needed by the new graceful-delete path.
    if (batch?.archiveEligible === true) return { eligible: true, reason: "" };
    if (batch?.archiveRequestEligible === true) {
      return {
        eligible: true,
        reason: "将先停止任务，等待 Runner、Bridge 和本地租约收尾后移入仓库",
        mode: "request",
        requestStatus,
      };
    }
    const reason = String(batch?.archiveRequestBlockedReason || batch?.archiveBlockedReason || "该批次当前无法安全删除");
    return { eligible: false, reason };
  }

  function pruneBatchArchiveSelection(batches, selectedIds) {
    const selected = selectedIds instanceof Set ? selectedIds : new Set(selectedIds || []);
    return new Set((Array.isArray(batches) ? batches : [])
      .filter((batch) => batchArchiveEligibility(batch).eligible && selected.has(String(batch?.id || "")))
      .map((batch) => String(batch.id)));
  }

  function archiveableBatchIds(batches) {
    return (Array.isArray(batches) ? batches : [])
      .filter((batch) => batchArchiveEligibility(batch).eligible)
      .map((batch) => String(batch.id));
  }

  const api = Object.freeze({
    PREVIEW_STATUS,
    REPOSITORY_SCOPE_LABEL,
    previewMeta,
    normalizePreview,
    buildImportSelection,
    flattenRepository,
    importResultSummary,
    shouldClearSubmittedInput,
    batchArchiveEligibility,
    pruneBatchArchiveSelection,
    archiveableBatchIds,
  });
  root.AmazonCategoryRepositoryUI = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : window));
