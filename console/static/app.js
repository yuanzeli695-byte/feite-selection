const state = {
  overview: null,
  batches: [],
  selectedId: localStorage.getItem("amazon-console-selected") || "",
  stream: null,
  streamBatchId: "",
  streamAfterByBatch: {},
  refreshing: false,
  activeStage: sessionStorage.getItem("amazon-console-stage") || "candidates",
  queueDrafts: {},
  mergedJsonDrafts: {},
  pasteValidationPending: {},
  categoryPreview: {
    status: "idle",
    source: "",
    items: [],
    selectedKeys: new Set(),
    error: "",
    requestId: 0,
    timer: null,
    controller: null,
  },
  categoryImportPending: false,
  repository: { status: "idle", query: "", rows: [], payload: null, error: "", requestId: 0, controller: null },
  archivedBatches: { status: "idle", items: [], error: "", requestId: 0, controller: null },
  repositoryTab: "records",
  batchArchiveSelection: new Set(),
  batchMutation: { batchId: "", batchIds: [], action: "" },
};

const categoryRepositoryUI = window.AmazonCategoryRepositoryUI;

const statusLabels = {
  created: "已创建",
  idle: "待开始",
  ready: "已就绪",
  waiting: "等待",
  running: "运行中",
  paused: "已暂停",
  needs_attention: "待确认",
  browser_waiting: "等待 Runner",
  excel_ready: "等待 JSON 交接",
  completed: "已完成",
  failed: "失败",
  cancelled: "已停止",
  stopping: "正在停止",
};

const archiveRequestLabels = {
  requested: "已提交停止请求",
  cancelling: "正在停止任务",
  waiting: "等待任务收尾",
  archived: "已移入仓库",
  failed: "删除收尾失败",
};

function archiveRequestLabel(status) {
  return archiveRequestLabels[String(status || "")] || "删除请求";
}

function archiveRequestTone(status) {
  if (status === "failed") return "bad";
  if (status === "archived") return "good";
  if (["requested", "cancelling", "waiting"].includes(status)) return "active";
  return "neutral";
}

function newIdempotencyKey() {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return `console-archive-${uuid}`;
  return `console-archive-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));
}

function tone(status) {
  if (["completed", "browser_waiting", "excel_ready", "ready"].includes(status)) return "good";
  if (["failed", "cancelled"].includes(status)) return "bad";
  if (["needs_attention", "paused"].includes(status)) return "warn";
  if (["running", "stopping"].includes(status)) return "active";
  return "neutral";
}

function dangdangButtonVariant(node) {
  if (node.classList.contains("primary")) return "dd-button--primary";
  if (node.classList.contains("danger")) return "dd-button--danger";
  if (node.classList.contains("quiet")) return "dd-button--ghost";
  return "dd-button--secondary";
}

function dangdangBadgeVariant(statusTone) {
  if (statusTone === "good") return "dd-badge--success";
  if (statusTone === "bad") return "dd-badge--error";
  if (statusTone === "warn") return "dd-badge--warning";
  if (statusTone === "active") return "dd-badge--info";
  return "dd-badge--neutral";
}

function upgradeDangdangBadge(node) {
  const statusTone = [...node.classList].find((name) => ["good", "bad", "warn", "active"].includes(name)) || "neutral";
  node.classList.add("dd-badge", "dd-badge--sm", dangdangBadgeVariant(statusTone));
}

function upgradeDangdangControls(root = document) {
  root.querySelectorAll("button.button, a.button").forEach((node) => {
    node.classList.add("dd-button", node.classList.contains("small") ? "dd-button--sm" : "dd-button--md", dangdangButtonVariant(node));
  });
  root.querySelectorAll("span.badge").forEach(upgradeDangdangBadge);
  root.querySelectorAll("span.version-badge").forEach((node) => {
    node.classList.add("dd-badge", "dd-badge--sm", "dd-badge--info");
  });
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

function shortHash(value) {
  return value ? `${String(value).slice(0, 10)}…` : "-";
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  } catch (error) {
    if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
      throw new Error("本地控制台未运行，请启动 http://127.0.0.1:8788");
    }
    throw error;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function fetchConsole(path, options = {}) {
  try {
    return await fetch(path, options);
  } catch (error) {
    if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
      throw new Error("本地控制台未运行，请启动 http://127.0.0.1:8788");
    }
    throw error;
  }
}

async function clipboardWrite(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const node = document.createElement("textarea");
    node.value = text;
    node.style.position = "fixed";
    node.style.opacity = "0";
    document.body.appendChild(node);
    node.select();
    document.execCommand("copy");
    node.remove();
  }
}

function toast(message, kind = "neutral") {
  const node = document.getElementById("toast");
  const variant = kind === "bad" ? "dd-toast--error" : kind === "warn" ? "dd-toast--warning" : kind === "good" ? "" : "dd-toast--info";
  node.className = `dd-toast dd-toast--entering ${variant}`.trim();
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 5000);
}

function selectedBatch() {
  return state.batches.find((batch) => batch.id === state.selectedId) || null;
}

function batchIsMutating(batchId) {
  return state.batchMutation.batchId === batchId || state.batchMutation.batchIds.includes(batchId);
}

async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    state.overview = await api("/api/overview");
    state.batches = state.overview.batches || [];
    if (state.selectedId && !selectedBatch()) state.selectedId = "";
    if (!state.selectedId && state.batches.length) state.selectedId = state.batches[0].id;
    render();
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    state.refreshing = false;
  }
}

function render() {
  renderHeader();
  renderCategoryPool();
  renderRuns();
  const batch = selectedBatch();
  document.getElementById("emptyState").hidden = Boolean(batch);
  document.getElementById("workflow").hidden = !batch;
  if (batch) {
    renderWorkflow(batch);
    if (["completed", "failed", "cancelled"].includes(batch.overallStatus)) closeStream();
    else ensureStream(batch.id);
  } else {
    closeStream();
  }
  if (document.getElementById("categoryRepositoryDialog").open) renderRepositoryManagement();
}

function renderCategoryPool() {
  const allItems = state.overview?.categoryPool || [];
  const items = allItems.filter((item) => ["available", "assigned"].includes(item.status));
  const counts = state.overview?.categoryPoolCounts || {};
  document.getElementById("poolAvailableCount").textContent = counts.available || 0;
  document.getElementById("poolAssignedCount").textContent = counts.assigned || 0;
  document.getElementById("poolRepositoryCount").textContent = state.overview?.categoryRepository?.counts?.categories || 0;
  document.getElementById("categoryRepositoryButton").disabled = state.overview?.features?.categoryRepository?.enabled === false;
  const root = document.getElementById("categoryPoolList");
  if (!items.length) {
    root.innerHTML = '<div class="pool-empty">暂无待分配或运行中的类目。</div>';
  } else {
    const poolLabels = { available: "未使用", assigned: "已分配" };
    root.innerHTML = items.map((item) => {
      const batchName = item.batchId ? escapeHtml(item.batchName || item.batchId) : "";
      const action = item.status === "available"
        ? `<button class="button primary small" data-pool-item="${escapeHtml(item.id)}" type="button">创建批次</button>`
        : `<button class="pool-batch-link" data-open-batch="${escapeHtml(item.batchId)}" type="button">查看批次</button>`;
      return `<div class="pool-row">
        <span title="${escapeHtml(item.input)}"><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.nodeIdPath || item.input)}</small></span>
        <span class="pool-row-status"><span class="badge ${item.status === "assigned" ? "active" : "neutral"}">${poolLabels[item.status] || escapeHtml(item.status)}</span>${batchName ? `<small title="${batchName}">${batchName}</small>` : ""}</span>
        <span>${action}</span>
      </div>`;
    }).join("");
    upgradeDangdangControls(root);
    root.querySelectorAll("[data-pool-item]").forEach((button) => button.addEventListener("click", () => {
      const item = items.find((candidate) => candidate.id === button.dataset.poolItem);
      if (item) openBatchDialog(item);
    }));
    root.querySelectorAll("[data-open-batch]").forEach((button) => button.addEventListener("click", () => {
      if (!state.batches.some((batch) => batch.id === button.dataset.openBatch)) return;
      state.selectedId = button.dataset.openBatch;
      localStorage.setItem("amazon-console-selected", state.selectedId);
      render();
      document.getElementById("workflow").scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }
  renderCategoryImportPreview();
}

function renderCategoryImportPreview() {
  const preview = state.categoryPreview;
  const root = document.getElementById("categoryImportPreview");
  const list = document.getElementById("categoryPreviewList");
  const summary = document.getElementById("categoryPreviewSummary");
  const submit = document.getElementById("categoryImportButton");
  const focusedKey = document.activeElement?.dataset?.previewKey || "";
  const source = document.getElementById("categoryPoolInput").value.trim();
  const current = Boolean(source) && preview.source === source;

  root.hidden = preview.status === "idle" && !source;
  root.setAttribute("aria-busy", preview.status === "pending" ? "true" : "false");
  if (!source) {
    summary.textContent = "";
    list.innerHTML = "";
    submit.textContent = "等待输入";
    submit.disabled = true;
    return;
  }
  if (!current || preview.status === "pending") {
    summary.textContent = "正在核对仓库与当前类目池";
    list.innerHTML = '<div class="preview-message"><span class="dd-spinner dd-spinner--sm" aria-hidden="true"><span></span></span>正在预检…</div>';
    submit.textContent = "预检中";
    submit.disabled = true;
    return;
  }
  if (preview.status === "error") {
    summary.textContent = "预检失败";
    list.innerHTML = `<div class="preview-message preview-error">${escapeHtml(preview.error || "无法完成类目预检")}</div>`;
    submit.textContent = "重新预检";
    submit.disabled = state.categoryImportPending;
    return;
  }

  const selection = categoryRepositoryUI.buildImportSelection(preview.items, preview.selectedKeys);
  const selectedCount = selection.selectedKeys.length;
  summary.textContent = `${preview.items.length} 行 · 已选 ${selectedCount}`;
  list.innerHTML = preview.items.length ? preview.items.map((item) => {
    const descriptionId = `category-preview-${item.line}-${String(item.key).replace(/[^A-Za-z0-9_-]/g, "-")}`;
    const checked = item.selectable && preview.selectedKeys.has(item.key);
    const node = item.nodeIdPath ? `<code>${escapeHtml(item.nodeIdPath)}</code>` : '<span class="preview-node-missing">未提供 nodeIdPath</span>';
    return `<label class="category-preview-row tone-${escapeHtml(item.tone)} ${item.selectable ? "" : "disabled"}">
      <input type="checkbox" data-preview-key="${escapeHtml(item.key)}" ${checked ? "checked" : ""} ${item.selectable ? "" : "disabled"} aria-describedby="${descriptionId}">
      <span class="preview-row-copy">
        <span class="preview-row-main"><strong><span class="preview-dot ${escapeHtml(item.tone)}" aria-hidden="true"></span>${escapeHtml(item.input || item.label || `第 ${item.line} 行`)}</strong>${node}</span>
        <small id="${descriptionId}"><b>${escapeHtml(item.statusLabel)}</b> · ${escapeHtml(item.statusDetail)}</small>
      </span>
    </label>`;
  }).join("") : '<div class="preview-message">没有可预检的类目行。</div>';
  list.querySelectorAll("[data-preview-key]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    if (checkbox.checked) preview.selectedKeys.add(checkbox.dataset.previewKey);
    else preview.selectedKeys.delete(checkbox.dataset.previewKey);
    renderCategoryImportPreview();
  }));
  if (focusedKey) list.querySelector(`[data-preview-key="${CSS.escape(focusedKey)}"]`)?.focus({ preventScroll: true });
  submit.textContent = state.categoryImportPending ? "正在导入" : `导入已选 ${selectedCount} 项`;
  submit.disabled = state.categoryImportPending || selectedCount === 0;
}

function scheduleCategoryPreview(immediate = false) {
  const preview = state.categoryPreview;
  const source = document.getElementById("categoryPoolInput").value.trim();
  clearTimeout(preview.timer);
  preview.controller?.abort();
  preview.controller = null;
  preview.requestId += 1;
  preview.source = source;
  preview.items = [];
  preview.selectedKeys = new Set();
  preview.error = "";
  if (!source) {
    preview.status = "idle";
    renderCategoryImportPreview();
    return;
  }
  preview.status = "pending";
  renderCategoryImportPreview();
  const requestId = preview.requestId;
  preview.timer = setTimeout(() => runCategoryPreview(source, requestId), immediate ? 0 : 350);
}

async function runCategoryPreview(source, requestId) {
  const preview = state.categoryPreview;
  const controller = new AbortController();
  preview.timer = null;
  preview.controller = controller;
  try {
    const payload = await api("/api/category-pool/preview", {
      method: "POST",
      body: JSON.stringify({ categories: source }),
      signal: controller.signal,
    });
    if (requestId !== preview.requestId || document.getElementById("categoryPoolInput").value.trim() !== source) return;
    const normalized = categoryRepositoryUI.normalizePreview(payload);
    preview.status = "ready";
    preview.items = normalized.items;
    preview.selectedKeys = new Set(normalized.selectedKeys);
    preview.error = "";
  } catch (error) {
    if (error.name === "AbortError" || requestId !== preview.requestId) return;
    preview.status = "error";
    preview.items = [];
    preview.selectedKeys = new Set();
    preview.error = error.message;
  } finally {
    if (preview.controller === controller) preview.controller = null;
    if (requestId === preview.requestId) renderCategoryImportPreview();
  }
}

function clearCategoryPreview() {
  const preview = state.categoryPreview;
  clearTimeout(preview.timer);
  preview.controller?.abort();
  preview.status = "idle";
  preview.source = "";
  preview.items = [];
  preview.selectedKeys = new Set();
  preview.error = "";
  preview.requestId += 1;
  preview.timer = null;
  preview.controller = null;
  renderCategoryImportPreview();
}

function openBatchDialog(item) {
  const form = document.getElementById("newBatchForm");
  form.reset();
  form.elements.categoryPoolItemId.value = item.id;
  form.elements.categories.value = item.input;
  const stamp = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date()).replace(/[/:]/g, "-").replace(/\s/g, "_");
  form.elements.name.value = `${item.label}_${stamp}`;
  document.getElementById("batchDialog").showModal();
}

function renderHeader() {
  const apiBadge = document.getElementById("apiBadge");
  const defaultSource = state.overview?.candidateSources?.default;
  const configured = state.overview?.sellerSpriteApi?.configured;
  apiBadge.textContent = defaultSource === "browser_export" ? "浏览器导出模式" : (configured ? "SellerSprite API 已配置" : "SellerSprite API 未配置");
  apiBadge.className = `badge ${defaultSource === "browser_export" || configured ? "good" : "bad"}`;
  const pair = state.overview?.approvedPair || {};
  const formal = state.overview?.preflight?.configuredBrowserPair?.formalRunAuthorized;
  const preflightMeta = state.overview?.preflightMeta || {};
  const pairBadge = document.getElementById("pairBadge");
  pairBadge.className = "badge neutral";
  const preflightLabel = preflightMeta.status === "checking" || preflightMeta.status === "refreshing"
    ? " · 预检检查中"
    : preflightMeta.status === "failed"
      ? " · 预检失败"
      : preflightMeta.status === "stale"
        ? " · 预检已过期"
        : "";
  pairBadge.textContent = `Bridge ${pair.bridge || "-"} / Collector ${pair.collector || "-"} / Runner ${pair.runner || "-"}${formal === false ? " · 候选验证中" : ""}${preflightLabel}`;
  pairBadge.title = preflightMeta.checkedAt
    ? `预检状态：${preflightMeta.status || "未知"}，最近检查：${formatTime(preflightMeta.checkedAt)}`
    : "预检尚未完成，正式派发仍会执行同步硬门禁";
  upgradeDangdangControls(document.querySelector(".app-header"));
}

function renderRuns() {
  const root = document.getElementById("runsList");
  state.batchArchiveSelection = categoryRepositoryUI.pruneBatchArchiveSelection(state.batches, state.batchArchiveSelection);
  renderBatchSelectionControls();
  if (!state.batches.length) {
    root.innerHTML = '<span class="muted">暂无批次</span>';
    return;
  }
  root.innerHTML = state.batches.map((batch) => {
    const archive = categoryRepositoryUI.batchArchiveEligibility(batch);
    const selected = state.batchArchiveSelection.has(batch.id);
    const mutating = batchIsMutating(batch.id);
    const archiveTitle = archive.reason || "删除后可在已完成选品类目库中恢复";
    const request = batch.archiveRequest;
    const requestStatus = String(request?.status || "");
    const requestNote = ["requested", "cancelling", "waiting", "failed"].includes(requestStatus)
      ? `<small class="run-archive-state ${archiveRequestTone(requestStatus)}" title="${escapeHtml(request?.lastError || archive.reason || "")}">删除：${escapeHtml(archiveRequestLabel(requestStatus))}${request?.lastError && requestStatus === "failed" ? ` · ${escapeHtml(request.lastError)}` : ""}</small>`
      : "";
    const archiveButtonLabel = archive.mode === "pending"
      ? "删除中"
      : archive.mode === "request"
        ? "停止并删除"
        : "删除";
    const archiveAriaLabel = archive.mode === "request" ? "停止并删除（可恢复）" : "删除（可恢复）";
    return `
    <div class="run-row ${batch.id === state.selectedId ? "selected" : ""}">
      <label class="run-select ${archive.eligible ? "" : "disabled"}" title="${escapeHtml(archiveTitle)}">
        <input data-select-batch="${escapeHtml(batch.id)}" type="checkbox" ${selected ? "checked" : ""} ${archive.eligible && !mutating ? "" : "disabled"} aria-label="选择批次 ${escapeHtml(batch.name)}">
      </label>
      <button class="run-tab" data-batch-id="${escapeHtml(batch.id)}" type="button" aria-pressed="${batch.id === state.selectedId ? "true" : "false"}">
        <span><strong>${escapeHtml(batch.name)}</strong><small>${escapeHtml(batch.category || "未分类")} · ${escapeHtml(batch.targetQualified)} 个目标</small></span>
        <span class="run-status-stack"><span class="badge ${tone(batch.overallStatus)}">${escapeHtml(statusLabels[batch.overallStatus] || batch.overallStatus)}</span>${requestNote}</span>
      </button>
      <button class="button quiet small run-archive" data-archive-batch="${escapeHtml(batch.id)}" type="button" title="${escapeHtml(archiveTitle)}" aria-label="${escapeHtml(archiveAriaLabel)}批次 ${escapeHtml(batch.name)}" ${archive.eligible && !mutating ? "" : "disabled"}>${archiveButtonLabel}</button>
    </div>`;
  }).join("");
  upgradeDangdangControls(root);
  root.querySelectorAll("[data-batch-id]").forEach((button) => button.addEventListener("click", () => {
    state.selectedId = button.dataset.batchId;
    localStorage.setItem("amazon-console-selected", state.selectedId);
    render();
  }));
  root.querySelectorAll("[data-archive-batch]").forEach((button) => button.addEventListener("click", () => {
    const batch = state.batches.find((item) => item.id === button.dataset.archiveBatch);
    if (batch) openArchiveDialog([batch]);
  }));
  root.querySelectorAll("[data-select-batch]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.batchArchiveSelection.add(checkbox.dataset.selectBatch);
    else state.batchArchiveSelection.delete(checkbox.dataset.selectBatch);
    renderRuns();
  }));
}

function renderBatchSelectionControls() {
  const eligibleIds = categoryRepositoryUI.archiveableBatchIds(state.batches);
  const selectedCount = state.batchArchiveSelection.size;
  const selectAll = document.getElementById("batchSelectAll");
  selectAll.checked = eligibleIds.length > 0 && selectedCount === eligibleIds.length;
  selectAll.indeterminate = selectedCount > 0 && selectedCount < eligibleIds.length;
  selectAll.disabled = eligibleIds.length === 0 || Boolean(state.batchMutation.action);
  document.getElementById("batchSelectedCount").textContent = `已选 ${selectedCount}`;
  document.getElementById("batchBulkDelete").disabled = selectedCount === 0 || Boolean(state.batchMutation.action);
}

function openArchiveDialog(batches) {
  const items = (Array.isArray(batches) ? batches : []).filter((batch) => categoryRepositoryUI.batchArchiveEligibility(batch).eligible);
  if (!items.length) return;
  const batchIds = items.map((batch) => batch.id);
  const requestMode = items.some((batch) => categoryRepositoryUI.batchArchiveEligibility(batch).mode === "request");
  const dialog = document.getElementById("batchArchiveDialog");
  dialog.dataset.requestMode = requestMode ? "request" : "archive";
  document.getElementById("batchArchiveIds").value = JSON.stringify(batchIds);
  document.getElementById("batchArchiveDescription").textContent = items.length === 1
    ? requestMode
      ? `确认停止并删除“${items[0].name}”？任务会先收尾，完成后自动移入可恢复仓库。`
      : `确认从当前列表删除“${items[0].name}”？`
    : requestMode
      ? `确认停止并删除已选择的 ${items.length} 个批次？运行中的批次会先收尾，完成后自动移入可恢复仓库。`
      : `确认从当前列表删除已选择的 ${items.length} 个批次？`;
  document.getElementById("batchArchiveConfirm").disabled = false;
  document.getElementById("batchArchiveConfirm").textContent = requestMode
    ? (items.length === 1 ? "停止并删除" : `停止并删除 ${items.length} 项`)
    : (items.length === 1 ? "确认删除" : `确认删除 ${items.length} 项`);
  dialog.showModal();
}

function setRepositoryTab(tabName) {
  state.repositoryTab = tabName === "archived" ? "archived" : "records";
  document.querySelectorAll("[data-repository-tab]").forEach((button) => {
    const active = button.dataset.repositoryTab === state.repositoryTab;
    button.classList.toggle("dd-tabs__item--active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  });
  document.getElementById("repositoryRecordsPanel").hidden = state.repositoryTab !== "records";
  document.getElementById("repositoryArchivedPanel").hidden = state.repositoryTab !== "archived";
}

function renderRepositoryManagement() {
  const repositoryHost = document.getElementById("categoryRepositoryTable");
  const repositorySummary = document.getElementById("categoryRepositorySummary");
  const archivedHost = document.getElementById("archivedBatchList");
  const repositoryCount = state.repository.rows.length;
  const archivedCount = state.archivedBatches.items.length || state.overview?.archivedBatchCount || 0;
  document.getElementById("repositoryRecordCount").textContent = repositoryCount;
  document.getElementById("repositoryArchivedCount").textContent = archivedCount;
  setRepositoryTab(state.repositoryTab);

  if (state.repository.status === "loading") {
    repositorySummary.textContent = "正在读取完成筛选记录";
    repositoryHost.innerHTML = '<div class="repository-loading"><span class="dd-spinner dd-spinner--md" aria-hidden="true"><span></span></span><span>正在加载仓库…</span></div>';
  } else if (state.repository.status === "error") {
    repositorySummary.textContent = "仓库读取失败";
    repositoryHost.innerHTML = `<div class="repository-empty repository-error">${escapeHtml(state.repository.error)}</div>`;
  } else {
    const total = Number(state.repository.payload?.counts?.completions || state.repository.rows.length || 0);
    repositorySummary.textContent = state.repository.query
      ? `找到 ${state.repository.rows.length} 条批次记录 · 仓库共 ${total} 条`
      : `共 ${state.repository.rows.length} 条完成批次记录`;
    repositoryHost.innerHTML = state.repository.rows.length ? `<div class="dd-table-wrapper repository-table-wrapper">
      <table class="dd-table repository-table">
        <thead class="dd-table__head"><tr class="dd-table__row">
          <th class="dd-table__header dd-table__cell--left" scope="col">类目</th>
          <th class="dd-table__header dd-table__cell--left" scope="col">nodeIdPath</th>
          <th class="dd-table__header dd-table__cell--left" scope="col">完成批次</th>
          <th class="dd-table__header dd-table__cell--left" scope="col">完成时间</th>
          <th class="dd-table__header dd-table__cell--left" scope="col">状态</th>
          <th class="dd-table__header dd-table__cell--right" scope="col">操作</th>
        </tr></thead>
        <tbody class="dd-table__body">${state.repository.rows.map((row) => `<tr class="dd-table__row">
          <td class="dd-table__cell"><strong>${escapeHtml(row.displayName)}</strong><small>${escapeHtml(row.marketplace)}</small></td>
          <td class="dd-table__cell repository-node"><code>${escapeHtml(row.nodeIdPath || "-")}</code></td>
          <td class="dd-table__cell"><strong>${escapeHtml(row.batchName)}</strong><small>${escapeHtml(row.batchId)}</small></td>
          <td class="dd-table__cell"><time datetime="${escapeHtml(row.completedAt)}">${escapeHtml(formatTime(row.completedAt))}</time></td>
          <td class="dd-table__cell"><span class="badge ${row.archived ? "neutral" : "good"}">${row.archived ? "已删除" : "当前列表"}</span></td>
          <td class="dd-table__cell dd-table__cell--right">${row.archived
            ? `<button class="button quiet small" data-show-archived="${escapeHtml(row.batchId)}" type="button">查看删除记录</button>`
            : `<button class="button quiet small" data-open-repository-batch="${escapeHtml(row.batchId)}" type="button">打开批次</button>`}</td>
        </tr>`).join("")}</tbody>
      </table>
    </div>` : '<div class="repository-empty">没有匹配的完成筛选记录。</div>';
  }

  if (state.archivedBatches.status === "loading") {
    archivedHost.innerHTML = '<div class="repository-loading"><span class="dd-spinner dd-spinner--md" aria-hidden="true"><span></span></span><span>正在加载已删除批次…</span></div>';
  } else if (state.archivedBatches.status === "error") {
    archivedHost.innerHTML = `<div class="repository-empty repository-error">${escapeHtml(state.archivedBatches.error)}</div>`;
  } else {
    archivedHost.innerHTML = state.archivedBatches.items.length ? state.archivedBatches.items.map((batch) => `
      <article class="archived-batch-row" data-archived-row="${escapeHtml(batch.id)}">
        <div><strong>${escapeHtml(batch.name)}</strong><small>${escapeHtml(batch.category || "未分类")}</small></div>
        <div class="archived-batch-meta"><span>原状态 ${escapeHtml(statusLabels[batch.overallStatus] || batch.overallStatus || "未知")}</span><span>删除 ${escapeHtml(formatTime(batch.archivedAt))}</span></div>
        <button class="button quiet small" data-restore-batch="${escapeHtml(batch.id)}" type="button" ${batchIsMutating(batch.id) ? "disabled" : ""}>${batchIsMutating(batch.id) ? "正在恢复" : "恢复"}</button>
      </article>`).join("") : '<div class="repository-empty">暂无已删除批次。</div>';
  }

  upgradeDangdangControls(document.getElementById("categoryRepositoryDialog"));
  repositoryHost.querySelectorAll("[data-open-repository-batch]").forEach((button) => button.addEventListener("click", () => {
    if (!state.batches.some((batch) => batch.id === button.dataset.openRepositoryBatch)) return;
    state.selectedId = button.dataset.openRepositoryBatch;
    localStorage.setItem("amazon-console-selected", state.selectedId);
    document.getElementById("categoryRepositoryDialog").close();
    render();
    document.getElementById("workflow").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  repositoryHost.querySelectorAll("[data-show-archived]").forEach((button) => button.addEventListener("click", () => {
    setRepositoryTab("archived");
    requestAnimationFrame(() => document.querySelector(`[data-archived-row="${CSS.escape(button.dataset.showArchived)}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }));
  archivedHost.querySelectorAll("[data-restore-batch]").forEach((button) => button.addEventListener("click", () => restoreArchivedBatch(button.dataset.restoreBatch)));
}

async function loadCategoryRepository(query = "") {
  const repository = state.repository;
  repository.controller?.abort();
  repository.requestId += 1;
  const requestId = repository.requestId;
  const controller = new AbortController();
  repository.controller = controller;
  repository.status = "loading";
  repository.query = String(query || "").trim();
  repository.error = "";
  renderRepositoryManagement();
  try {
    const payload = await api(`/api/category-repository?q=${encodeURIComponent(repository.query)}`, { signal: controller.signal });
    if (requestId !== repository.requestId) return;
    repository.payload = payload;
    repository.rows = categoryRepositoryUI.flattenRepository(payload);
    repository.status = "ready";
  } catch (error) {
    if (error.name === "AbortError" || requestId !== repository.requestId) return;
    repository.status = "error";
    repository.error = error.message;
    repository.rows = [];
  } finally {
    if (repository.controller === controller) repository.controller = null;
    if (requestId === repository.requestId) renderRepositoryManagement();
  }
}

async function loadArchivedBatches() {
  const archived = state.archivedBatches;
  archived.controller?.abort();
  archived.requestId += 1;
  const requestId = archived.requestId;
  const controller = new AbortController();
  archived.controller = controller;
  archived.status = "loading";
  archived.error = "";
  renderRepositoryManagement();
  try {
    const payload = await api("/api/batches?archived=1", { signal: controller.signal });
    if (requestId !== archived.requestId) return;
    archived.items = Array.isArray(payload.batches) ? payload.batches : [];
    archived.status = "ready";
  } catch (error) {
    if (error.name === "AbortError" || requestId !== archived.requestId) return;
    archived.status = "error";
    archived.error = error.message;
  } finally {
    if (archived.controller === controller) archived.controller = null;
    if (requestId === archived.requestId) renderRepositoryManagement();
  }
}

async function openRepositoryManagement() {
  const dialog = document.getElementById("categoryRepositoryDialog");
  state.repositoryTab = "records";
  if (!dialog.open) dialog.showModal();
  renderRepositoryManagement();
  await Promise.all([
    loadCategoryRepository(document.getElementById("categoryRepositorySearch").value),
    loadArchivedBatches(),
  ]);
}

async function restoreArchivedBatch(batchId) {
  if (!batchId || state.batchMutation.action) return;
  state.batchMutation = { batchId, batchIds: [batchId], action: "restore" };
  renderRepositoryManagement();
  try {
    await api(`/api/batches/${batchId}/restore`, { method: "POST", body: "{}" });
    await Promise.all([refresh(), loadArchivedBatches(), loadCategoryRepository(state.repository.query)]);
    toast("批次已恢复到当前列表", "good");
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    state.batchMutation = { batchId: "", batchIds: [], action: "" };
    renderRepositoryManagement();
  }
}

function stageHeader(index, title, subtitle, stage) {
  const recovery = stage.recovery || stage.artifacts?.recovery;
  const recoveryHint = recovery?.canRetry
    ? `<small class="stage-recovery-hint">${escapeHtml(recovery.processAlive ? "服务重启后发现遗留进程，未自动接管" : "服务重启导致任务中断，可安全重试")}</small>`
    : "";
  return `<div class="stage-head"><div><span class="stage-number">${index}</span><h3>${title}</h3><p>${subtitle}</p></div><span class="badge ${tone(stage.status)}">${escapeHtml(statusLabels[stage.status] || stage.status)}</span></div><p class="stage-message">${escapeHtml(stage.message || "-")}</p>${recoveryHint}`;
}

function renderStageNavigation(batch) {
  const stages = ["candidates", "browser", "excel"];
  if (!stages.includes(state.activeStage)) state.activeStage = "candidates";
  const statusTargets = {
    candidates: "candidateTabStatus",
    browser: "browserTabStatus",
    excel: "excelTabStatus",
  };
  stages.forEach((key) => {
    const stage = batch.stages[key];
    const tab = document.querySelector(`[data-stage-tab="${key}"]`);
    const panel = document.querySelector(`[data-stage="${key}"]`);
    const active = state.activeStage === key;
    tab.classList.toggle("active", active);
    tab.dataset.tone = tone(stage.status);
    tab.setAttribute("aria-current", active ? "step" : "false");
    panel.hidden = !active;
    document.getElementById(statusTargets[key]).textContent = statusLabels[stage.status] || stage.status;
    tab.onclick = () => {
      state.activeStage = key;
      sessionStorage.setItem("amazon-console-stage", key);
      renderStageNavigation(batch);
    };
  });
}

function artifactLink(batch, key, label) {
  return `<a class="button quiet small" href="/api/batches/${batch.id}/artifact?key=${key}" target="_blank">${label}</a>`;
}

function renderCandidateStage(batch) {
  const root = document.getElementById("candidateStage");
  const stage = batch.stages.candidates;
  const artifacts = stage.artifacts || {};
  const categories = batch.categoryPool || [];
  const filters = batch.queryFilters || {};
  const browserExport = batch.candidateSourceMode === "browser_export";
  const exportTasks = artifacts.exportTasks || [];
  const sellerSpriteBridge = artifacts.sellerSpriteBridge || {};
  const categoryHtml = categories.length ? categories.map((item) => `
    <div class="category-row"><span>${escapeHtml(item.input)}</span><small>${escapeHtml(item.nodeLabelPathLocale || item.nodeLabelPath || "待解析")}</small><span class="status-dot ${item.status === "resolved" ? "good" : item.status === "needs_resolution" ? "bad" : "neutral"}"></span></div>`).join("") : '<div class="muted">旧版 SellerSprite 导出批次</div>';
  const filterText = [
    `$${filters.minPrice ?? 9.9}–${filters.maxPrice ?? 50}`,
    `评分 ≥ ${filters.minRating ?? 4}`,
    `评论 ≤ ${filters.maxReviews ?? 100}`,
    `子体销量 ${filters.minChildSales ?? 50}–${filters.maxChildSales ?? 300}`,
    `变体 ≤ ${filters.maxVariations ?? 25}`,
    `上架 ≤ ${filters.availableMonth ?? 3} 月`,
  ].join(" · ");
  const allExportsUploaded = exportTasks.length > 0 && exportTasks.every((item) => item.uploaded);
  const bridgeEnabled = browserExport && Boolean(state.overview?.sellerSpriteBridge?.enabled);
  const bridgeStatus = String(sellerSpriteBridge.status || "");
  const uploadedExportCount = Number(artifacts.uploadedExportCount || exportTasks.filter((item) => item.uploaded).length || 0);
  const bridgeBusy = bridgeEnabled && (bridgeStatus === "queued" || bridgeStatus === "processing" || (bridgeStatus === "uploaded" && !allExportsUploaded));
  const bridgeStatusText = {
    queued: "已自动排队，等待 SellerSprite",
    processing: "导出已齐，正在生成 ASIN",
    uploaded: allExportsUploaded ? "导出已回传，正在生成 ASIN" : `已回传 ${uploadedExportCount}/${exportTasks.length}`,
    asin_ready: "ASIN 队列已生成",
    needs_attention: "自动流程待处理",
    manual_required: "等待人工上传",
  }[bridgeStatus] || (bridgeEnabled ? "自动流程待启动" : "人工上传模式");
  const bridgeTone = ["uploaded", "asin_ready"].includes(bridgeStatus) ? "good" : ["needs_attention", "manual_required"].includes(bridgeStatus) ? "warn" : ["queued", "processing"].includes(bridgeStatus) ? "active" : "neutral";
  const recoveryBlocked = Boolean(stage.recovery?.canRetry || artifacts.recovery?.canRetry);
  const canStart = ["idle", "failed", "cancelled"].includes(stage.status) || (browserExport && stage.status === "needs_attention" && !recoveryBlocked && !artifacts.queuePath && !bridgeBusy);
  const canApprove = stage.status === "needs_attention" && Boolean(artifacts.queuePath);
  const canRetryRecovery = stage.status === "needs_attention" && Boolean(stage.recovery?.canRetry || artifacts.recovery?.canRetry);
  const queueDraft = state.queueDrafts[batch.id] || "";
  const automaticExportRows = exportTasks.map((task) => `
    <div class="export-task-row automatic" data-export-index="${escapeHtml(task.categoryInput)}">
      <strong>${escapeHtml(task.categoryInput)}</strong>
      <span class="badge ${task.uploaded ? "good" : "neutral"}">${task.uploaded ? `已回传 ${escapeHtml(task.fileName || "导出表格")}` : "等待 Bridge 自动导出"}</span>
      <small>${task.uploaded ? escapeHtml(task.capturedAt ? `采集于 ${formatTime(task.capturedAt)}` : "来源已校验") : "Bridge 将自动打开查询、导出并回传表格"}</small>
    </div>`).join("");
  const manualExportRows = exportTasks.map((task, index) => `
    <div class="export-task-row" data-export-index="${index}">
      <strong>${escapeHtml(task.categoryInput)}</strong>
      <span class="badge ${task.uploaded ? "good" : "neutral"}">${task.uploaded ? escapeHtml(task.fileName) : "待上传"}</span>
      <input data-export-url type="url" value="${escapeHtml(task.queryUrl || "")}" placeholder="当前 SellerSprite 完整筛选 URL">
      <input data-export-file type="file" accept=".xlsx,.csv,.tsv">
      <div class="export-actions">
        ${task.queryUrl ? `<a class="button quiet small" href="${escapeHtml(task.queryUrl)}" target="_blank">打开查询</a>` : ""}
        <button class="button ${task.uploaded ? "quiet" : "primary"} small" data-upload-export type="button">${task.uploaded ? "替换导出" : "上传导出"}</button>
      </div>
    </div>`).join("");
  const exportHtml = browserExport && exportTasks.length ? `<div class="source-bridge-line"><span class="badge ${bridgeTone}">${escapeHtml(bridgeStatusText)}</span>${bridgeEnabled ? `<span class="muted">${allExportsUploaded ? "所有类目已回传，控制台将自动生成 ASIN 队列" : "创建批次后自动查询、导出并回传"}</span>` : ""}<a class="button quiet small" href="/seller-sprite-bridge.user.js" target="_blank">安装 SellerSprite Bridge</a><button class="button quiet small" data-action="copy-sellersprite-pairing" type="button">复制配对码</button></div><div class="export-task-list">${bridgeEnabled ? automaticExportRows : manualExportRows}</div>${bridgeEnabled ? `<details class="manual-export-fallback"><summary>人工回退上传</summary><p class="muted">仅在 Bridge 未配对或站点无法自动导出时使用；文件仍会经过同一套类目、筛选 URL 和时间校验。</p><div class="export-task-list">${manualExportRows}</div></details>` : ""}` : "";
  const prepareLabel = browserExport ? (allExportsUploaded ? "重新生成 ASIN 队列" : bridgeEnabled ? (bridgeStatus === "needs_attention" ? "重试自动导出" : "启动自动查询与导出") : (exportTasks.length ? "重新发送未完成导出" : "发送到 SellerSprite")) : "开始准备 ASIN";
  root.innerHTML = `${stageHeader("01", "类目池与 ASIN 准备", browserExport ? "SellerSprite 浏览器导出 / 严格预筛" : "SellerSprite Open API / 严格预筛", stage)}
    <div class="stage-section"><div class="section-label"><span>类目</span><strong>${categories.length || 1}</strong></div><div class="category-list">${categoryHtml}</div></div>
    <div class="filter-summary">${escapeHtml(filterText)}</div>
    ${exportHtml}
    <div class="metrics three"><div><span>源候选</span><strong>${artifacts.sourceRowCount ?? artifacts.uploadedExportCount ?? "-"}</strong></div><div><span>Runner 队列</span><strong>${artifacts.queueCount ?? "-"}</strong></div><div><span>主图目录</span><strong>${artifacts.imagesDir ? "就绪" : "-"}</strong></div></div>
    <textarea id="queueEditor" class="queue-editor" rows="7" placeholder="Runner ASIN 队列；加载后可删减，一行一个">${escapeHtml(queueDraft)}</textarea>
    <div class="stage-actions">
      ${canStart ? `<button class="button primary" data-action="prepare-candidates" type="button">${prepareLabel}</button>` : ""}
      ${canRetryRecovery ? '<button class="button quiet" data-action="retry-recovery" type="button">从中断任务重试</button>' : ""}
      ${artifacts.queuePath ? '<button class="button quiet" data-action="load-queue" type="button">加载 ASIN 队列</button>' : ""}
      ${canApprove ? '<button class="button primary" data-action="approve-queue" type="button">确认 Runner 队列</button>' : ""}
      ${artifacts.analysisWorkbookPath ? artifactLink(batch, "analysisWorkbook", "打开候选分析表") : ""}
      ${artifacts.candidateSummary || artifacts.summaryPath ? artifactLink(batch, "candidateSummary", "查看预筛摘要") : ""}
    </div>`;

  upgradeDangdangControls(root);
  root.querySelector("#queueEditor")?.addEventListener("input", (event) => {
    state.queueDrafts[batch.id] = event.currentTarget.value;
  });
  root.querySelector('[data-action="prepare-candidates"]')?.addEventListener("click", () => postAction(batch.id, "candidates", {}));
  root.querySelector('[data-action="retry-recovery"]')?.addEventListener("click", () => postAction(batch.id, "retry", { stage: "candidates" }));
  root.querySelector('[data-action="copy-sellersprite-pairing"]')?.addEventListener("click", async () => {
    try {
      const data = await api("/api/sellersprite/pairing");
      await clipboardWrite(data.pairingToken);
      toast("SellerSprite Bridge 配对码已复制", "good");
    } catch (error) { toast(error.message, "bad"); }
  });
  root.querySelectorAll("[data-upload-export]").forEach((button) => button.addEventListener("click", async () => {
    const row = button.closest("[data-export-index]");
    const task = exportTasks[Number(row.dataset.exportIndex)];
    const file = row.querySelector("[data-export-file]").files[0];
    const queryUrl = row.querySelector("[data-export-url]").value.trim();
    if (!file) return toast("请选择 SellerSprite 导出文件", "warn");
    if (!queryUrl) return toast("请粘贴当前 SellerSprite 完整筛选 URL", "warn");
    button.disabled = true;
    try {
      const params = new URLSearchParams({ categoryInput: task.categoryInput, sourcePage: task.label || task.categoryInput, queryUrl });
      const response = await fetchConsole(`/api/batches/${batch.id}/candidate-export?${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) },
        body: file,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `上传失败 HTTP ${response.status}`);
      toast(`已上传 ${file.name}`, "good");
      await refresh();
    } catch (error) {
      toast(error.message, "bad");
    } finally {
      button.disabled = false;
    }
  }));
  root.querySelector('[data-action="load-queue"]')?.addEventListener("click", async () => {
    try {
      const response = await fetchConsole(`/api/batches/${batch.id}/artifact?key=queue`);
      if (!response.ok) throw new Error(`队列加载失败 HTTP ${response.status}`);
      const queue = await response.text();
      state.queueDrafts[batch.id] = queue;
      root.querySelector("#queueEditor").value = queue;
    } catch (error) { toast(error.message, "bad"); }
  });
  root.querySelector('[data-action="approve-queue"]')?.addEventListener("click", async () => {
    try {
      const selectedAsins = root.querySelector("#queueEditor").value;
      if (!selectedAsins.trim()) return toast("Runner 队列不能为空；请至少保留一个 ASIN", "warn");
      await api(`/api/batches/${batch.id}/approve-candidates`, { method: "POST", body: JSON.stringify({ selectedAsins }) });
      delete state.queueDrafts[batch.id];
      toast("Runner 队列已确认", "good");
      await refresh();
    } catch (error) { toast(error.message, "bad"); }
  });
}

function renderBrowserStage(batch) {
  const root = document.getElementById("browserStage");
  const stage = batch.stages.browser;
  const stats = stage.stats || {};
  const connection = stage.connection || {};
  const handoff = batch.jsonHandoff || {};
  const runnerAlreadyDelivered = stage.status === "completed" || Boolean(handoff.sourcePath);
  const total = Number(stats.total || batch.stages.candidates.artifacts?.queueCount || 0);
  const completed = Number(stats.completed || stats.resultCount || 0);
  const progress = total ? Math.min(100, Math.round(completed / total * 100)) : 0;
  const pair = state.overview?.preflight?.configuredBrowserPair || {};
  root.innerHTML = `${stageHeader("02", "导入 Runner 并筛选", "Amazon US / Collector / Runner", stage)}
    <div class="connection-line"><span class="status-dot ${connection.status === "connected" ? "good" : "neutral"}"></span><span>${connection.status === "connected" ? "Bridge 已连接" : "Bridge 等待命令"}</span><small>${formatTime(connection.lastHeartbeat || stats.lastHeartbeat)}</small></div>
    <div class="dd-progress dd-progress--md" style="--dd-progress-value: ${progress}%" role="progressbar" aria-label="Runner 进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><span class="dd-progress__bar"></span></div>
    <div class="metrics four"><div><span>进度</span><strong>${completed}/${total || "-"}</strong></div><div><span>通过</span><strong>${stats.qualifiedCount ?? "-"}</strong></div><div><span>拒绝</span><strong>${stats.rejectedCount ?? "-"}</strong></div><div><span>异常</span><strong>${stats.errorCount ?? "-"}</strong></div></div>
    <div class="current-row"><span>当前 ASIN</span><strong>${escapeHtml(stats.asin || "等待")}</strong><small>${escapeHtml(stats.gate || stats.message || "-")}</small></div>
    <div class="stage-actions">
      <button class="button quiet" data-action="copy-pairing" type="button">复制一次性配对码</button>
      <button class="button primary" data-runner-command="start" type="button" ${batch.stages.candidates.status !== "completed" || runnerAlreadyDelivered ? "disabled" : ""}>接管或启动 Runner</button>
      <button class="button quiet" data-runner-command="pause" type="button">暂停</button>
      <button class="button quiet" data-runner-command="resume" type="button">继续</button>
      <button class="button quiet" data-runner-command="export" type="button">请求导出</button>
      <button class="button primary" data-action="copy-json" type="button" ${handoff.sourcePath ? "" : "disabled"}>复制合并 JSON</button>
    </div>
    <div class="hash-line"><span>Runner 批次</span><code>${escapeHtml(batch.runnerBatchName || "-")}</code><span>JSON</span><code>${escapeHtml(shortHash(handoff.sourceSha256))}</code></div>
    ${pair.formalRunAuthorized === false ? '<div class="mode-banner">候选脚本组合：技术适配完成，正式放量前仍需单 ASIN 现场 smoke 与 30-ASIN 配对证据</div>' : ""}`;

  upgradeDangdangControls(root);
  root.querySelector('[data-action="copy-pairing"]')?.addEventListener("click", async () => {
    try {
      const data = await api("/api/bridge/pairing");
      await clipboardWrite(data.pairingToken);
      toast("Bridge 配对码已复制；只需在 Amazon Bridge v2 中配对一次", "good");
    } catch (error) { toast(error.message, "bad"); }
  });
  root.querySelectorAll("[data-runner-command]").forEach((button) => button.addEventListener("click", () => postAction(batch.id, "browser", { command: button.dataset.runnerCommand })));
  root.querySelector('[data-action="copy-json"]')?.addEventListener("click", async () => {
    try {
      const data = await api(`/api/batches/${batch.id}/copy-json`, { method: "POST", body: "{}" });
      await clipboardWrite(data.text);
      toast("合并 JSON 已复制，请手动粘贴到 03 区", "good");
      await refresh();
    } catch (error) { toast(error.message, "bad"); }
  });
}

function renderExcelStage(batch) {
  const root = document.getElementById("excelStage");
  const draftSnapshot = window.AmazonConsoleJsonDraft.capture(
    root.querySelector("#mergedPaste"),
    document.activeElement,
    state.mergedJsonDrafts,
  );
  const stage = batch.stages.excel;
  const artifacts = stage.artifacts || {};
  const handoff = batch.jsonHandoff || {};
  const sourceSha256 = String(handoff.sourceSha256 || "");
  const sourceReady = Boolean(handoff.sourcePath && sourceSha256);
  const mergedJsonDraft = window.AmazonConsoleJsonDraft.valueFor(state.mergedJsonDrafts, batch.id, sourceSha256);
  const validationPending = Boolean(state.pasteValidationPending[batch.id]);
  const canValidate = sourceReady && Boolean(mergedJsonDraft.trim()) && !validationPending;
  const recoveryBlocked = Boolean(stage.recovery?.canRetry || artifacts.recovery?.canRetry);
  root.innerHTML = `${stageHeader("03", "粘贴 JSON 并生成 Excel", "人工交接 / direct_import", stage)}
    <div class="handoff-state ${handoff.pasteVerified ? "verified" : ""}"><span>${handoff.pasteVerified ? "哈希一致" : "等待粘贴"}</span><code>${escapeHtml(shortHash(handoff.pastedSha256 || handoff.sourceSha256))}</code></div>
    <textarea id="mergedPaste" class="json-editor" rows="13" spellcheck="false" data-batch-id="${escapeHtml(batch.id)}" data-source-sha256="${escapeHtml(sourceSha256)}" data-draft-version="${window.AmazonConsoleJsonDraft.VERSION}" placeholder="在此手动粘贴 02 区复制的合并 JSON"></textarea>
    <div class="metrics two"><div><span>导入行</span><strong>${stage.stats?.rowCount ?? artifacts.rowCount ?? "-"}</strong></div><div><span>嵌入主图</span><strong>${stage.stats?.embeddedImageCount ?? artifacts.embeddedImageCount ?? "-"}</strong></div></div>
    <div class="stage-actions">
      <button class="button ${handoff.pasteVerified ? "quiet" : "primary"}" data-action="validate-paste" type="button" ${canValidate ? "" : "disabled"}>${validationPending ? "正在校验 JSON" : "校验粘贴 JSON"}</button>
      <button class="button primary" data-action="build-excel" type="button" ${handoff.pasteVerified && !recoveryBlocked ? "" : "disabled"}>生成 direct_import Excel</button>
      ${stage.status === "needs_attention" && (stage.recovery?.canRetry || artifacts.recovery?.canRetry) ? '<button class="button quiet" data-action="retry-recovery" type="button">从中断任务重试</button>' : ""}
      ${artifacts.workbookPath ? artifactLink(batch, "workbook", "下载 Excel") : ""}
    </div>
    <div class="mode-banner">direct_import · 不更新严格合格历史</div>`;

  upgradeDangdangControls(root);
  const mergedPaste = root.querySelector("#mergedPaste");
  const validateButton = root.querySelector('[data-action="validate-paste"]');
  window.AmazonConsoleJsonDraft.bind(mergedPaste, batch.id, sourceSha256, state.mergedJsonDrafts, draftSnapshot, (value) => {
    window.AmazonConsoleJsonDraft.setDisabled(validateButton, !sourceReady || !value.trim() || Boolean(state.pasteValidationPending[batch.id]));
  });
  validateButton?.addEventListener("click", async () => {
    if (state.pasteValidationPending[batch.id]) return;
    const mergedJson = mergedPaste.value.trim();
    if (!mergedJson) return toast("请先粘贴合并 JSON", "warn");
    state.pasteValidationPending[batch.id] = true;
    window.AmazonConsoleJsonDraft.setDisabled(validateButton, true);
    validateButton.textContent = "正在校验 JSON";
    try {
      const result = await api(`/api/batches/${batch.id}/paste-json`, { method: "POST", body: JSON.stringify({ mergedJson }) });
      delete state.mergedJsonDrafts[batch.id];
      delete state.pasteValidationPending[batch.id];
      const batchIndex = state.batches.findIndex((item) => item.id === batch.id);
      if (batchIndex >= 0) state.batches[batchIndex] = result.batch;
      render();
      toast("粘贴 JSON 与 Runner 原件一致", "good");
      await refresh();
    } catch (error) {
      delete state.pasteValidationPending[batch.id];
      if (selectedBatch()?.id === batch.id) renderExcelStage(selectedBatch());
      toast(error.message, "bad");
    }
  });
  root.querySelector('[data-action="build-excel"]')?.addEventListener("click", () => postAction(batch.id, "excel", {}));
  root.querySelector('[data-action="retry-recovery"]')?.addEventListener("click", () => postAction(batch.id, "retry", { stage: "excel" }));
}

function renderWorkflow(batch) {
  document.getElementById("batchTitle").textContent = batch.name;
  document.getElementById("batchMeta").textContent = `BATCH ${batch.id} · ${batch.operator} · ${formatTime(batch.createdAt)}`;
  const status = document.getElementById("overallStatus");
  status.textContent = statusLabels[batch.overallStatus] || batch.overallStatus;
  status.className = `badge ${tone(batch.overallStatus)}`;
  upgradeDangdangBadge(status);
  const stopButton = document.getElementById("stopButton");
  const stopping = batch.overallStatus === "stopping";
  const terminal = ["completed", "failed", "cancelled"].includes(batch.overallStatus);
  const archiveStatus = String(batch.archiveRequest?.status || "");
  const archivePending = ["requested", "cancelling", "waiting"].includes(archiveStatus);
  stopButton.hidden = terminal || archivePending;
  stopButton.disabled = terminal || archivePending;
  stopButton.textContent = stopping ? "重试停止" : "停止";
  const archiveRequestStatus = document.getElementById("archiveRequestStatus");
  if (archiveRequestStatus) {
    const visible = archivePending || archiveStatus === "failed";
    archiveRequestStatus.hidden = !visible;
    archiveRequestStatus.className = `archive-request-status ${archiveRequestTone(archiveStatus)}`;
    archiveRequestStatus.textContent = visible
      ? `删除请求：${archiveRequestLabel(archiveStatus)}${batch.archiveRequest?.lastError ? ` · ${batch.archiveRequest.lastError}` : ""}`
      : "";
    archiveRequestStatus.title = batch.archiveRequest?.phase || "";
  }
  renderCandidateStage(batch);
  renderBrowserStage(batch);
  renderExcelStage(batch);
  renderStageNavigation(batch);
  renderEvents(batch);
}

function renderEvents(batch) {
  const events = (batch.events || []).slice().reverse().slice(0, 60);
  document.getElementById("eventCount").textContent = `${events.length} 条`;
  document.getElementById("eventLog").innerHTML = events.length ? events.map((event) => `
    <div class="event-row"><time>${formatTime(event.at)}</time><span class="level ${escapeHtml(event.level)}">${escapeHtml(event.level)}</span><span>${escapeHtml(event.message)}</span></div>`).join("") : '<span class="muted">暂无日志</span>';
}

async function postAction(batchId, action, payload) {
  try {
    await api(`/api/batches/${batchId}/${action}`, { method: "POST", body: JSON.stringify(payload || {}) });
    toast("命令已提交", "good");
    await refresh();
  } catch (error) {
    toast(error.message, "bad");
  }
}

function ensureStream(batchId) {
  if (state.streamBatchId === batchId && state.stream) return;
  closeStream();
  state.streamBatchId = batchId;
  const after = Number(state.streamAfterByBatch[batchId] || 0);
  state.stream = new EventSource(`/api/batches/${batchId}/stream?after=${after}`);
  state.stream.onmessage = (event) => {
    const eventId = Number(event.lastEventId || 0);
    if (eventId) state.streamAfterByBatch[batchId] = eventId;
    refresh();
  };
  state.stream.onerror = () => {
    closeStream();
    setTimeout(() => selectedBatch() && ensureStream(state.selectedId), 3000);
  };
}

function closeStream() {
  state.stream?.close();
  state.stream = null;
  state.streamBatchId = "";
}

upgradeDangdangControls(document);
const initialToast = document.getElementById("toast");
initialToast.hidden = true;
document.getElementById("refreshButton").addEventListener("click", refresh);
document.getElementById("categoryRepositoryButton").addEventListener("click", openRepositoryManagement);
document.getElementById("newBatchButton").addEventListener("click", () => {
  document.getElementById("categoryPoolInput").scrollIntoView({ behavior: "smooth", block: "center" });
  document.getElementById("categoryPoolInput").focus();
});
document.getElementById("batchSelectAll").addEventListener("change", (event) => {
  state.batchArchiveSelection = event.currentTarget.checked
    ? new Set(categoryRepositoryUI.archiveableBatchIds(state.batches))
    : new Set();
  renderRuns();
});
document.getElementById("batchBulkDelete").addEventListener("click", () => {
  const batches = state.batches.filter((batch) => state.batchArchiveSelection.has(batch.id));
  openArchiveDialog(batches);
});
document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog")?.close()));
const repositoryTabs = [...document.querySelectorAll("[data-repository-tab]")];
repositoryTabs.forEach((button, index) => {
  button.addEventListener("click", () => setRepositoryTab(button.dataset.repositoryTab));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const targetIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? repositoryTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + repositoryTabs.length) % repositoryTabs.length;
    const target = repositoryTabs[targetIndex];
    setRepositoryTab(target.dataset.repositoryTab);
    target.focus();
  });
});
document.getElementById("categoryRepositorySearchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(loadCategoryRepository.timer);
  loadCategoryRepository(document.getElementById("categoryRepositorySearch").value);
});
document.getElementById("categoryRepositorySearch").addEventListener("input", (event) => {
  clearTimeout(loadCategoryRepository.timer);
  const query = event.currentTarget.value;
  loadCategoryRepository.timer = setTimeout(() => loadCategoryRepository(query), 350);
});
document.getElementById("stopButton").addEventListener("click", () => {
  const batch = selectedBatch();
  if (!batch) return;
  const message = batch.overallStatus === "stopping"
    ? "重新发送停止命令？现有停止意图和 Bridge 租约会继续保留。"
    : "停止当前批次？若 Runner 正在处理 ASIN，将在当前行完成后停止；已落盘产物不会删除。";
  if (confirm(message)) postAction(batch.id, "stop", {});
});

document.getElementById("batchArchiveForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  let batchIds = [];
  try {
    batchIds = JSON.parse(document.getElementById("batchArchiveIds").value || "[]");
  } catch (_) {
    batchIds = [];
  }
  batchIds = [...new Set(batchIds.map(String).filter(Boolean))];
  if (!batchIds.length || state.batchMutation.action) return;
  const confirmButton = document.getElementById("batchArchiveConfirm");
  const archiveDialog = document.getElementById("batchArchiveDialog");
  const requestMode = archiveDialog.dataset.requestMode === "request";
  state.batchMutation = { batchId: batchIds.length === 1 ? batchIds[0] : "", batchIds, action: requestMode ? "archive-request" : "archive" };
  confirmButton.disabled = true;
  confirmButton.textContent = requestMode
    ? (batchIds.length === 1 ? "正在停止并删除" : `正在停止并删除 ${batchIds.length} 项`)
    : (batchIds.length === 1 ? "正在删除" : `正在删除 ${batchIds.length} 项`);
  renderRuns();
  try {
    const endpoint = requestMode ? "/api/batches/archive-request" : "/api/batches/archive";
    const options = { method: "POST", body: JSON.stringify({ batchIds }) };
    if (requestMode) options.headers = { "Content-Type": "application/json", "Idempotency-Key": newIdempotencyKey() };
    const result = await api(endpoint, options);
    archiveDialog.close();
    batchIds.forEach((batchId) => state.batchArchiveSelection.delete(batchId));
    const archivedCount = Number(result?.archivedCount || 0);
    const pendingCount = Number(result?.pendingCount || 0);
    const failedCount = Array.isArray(result?.failed) ? result.failed.length : 0;
    if (!pendingCount && !failedCount && batchIds.includes(state.selectedId)) {
      state.selectedId = "";
      localStorage.removeItem("amazon-console-selected");
      closeStream();
    }
    await refresh();
    if (document.getElementById("categoryRepositoryDialog").open) {
      await Promise.all([loadArchivedBatches(), loadCategoryRepository(state.repository.query)]);
    }
    if (pendingCount) {
      toast(`${pendingCount} 个批次已提交停止并删除，控制台会等待任务收尾后自动移入可恢复仓库`, "warn");
    } else if (failedCount) {
      toast(`${archivedCount} 个批次已删除，另有 ${failedCount} 个批次未能安全收尾，请查看原因后重试`, "warn");
    } else {
      toast(`${archivedCount || batchIds.length} 个批次已删除，可在已完成选品类目库恢复；完成记录、日志和产物仍保留`, "good");
    }
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    state.batchMutation = { batchId: "", batchIds: [], action: "" };
    confirmButton.disabled = false;
    confirmButton.textContent = "确认删除";
    renderRuns();
  }
});

document.getElementById("newBatchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const categories = String(form.get("categories") || "").trim();
  const now = new Date();
  const autoName = `类目池 ${now.toISOString().slice(0, 10)} ${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
  const filters = {};
  ["minPrice", "maxPrice", "minRating", "minReviews", "maxReviews", "minChildSales", "maxChildSales", "minVariations", "maxVariations", "availableMonth", "perCategoryLimit"].forEach((key) => { filters[key] = Number(form.get(key)); });
  const payload = {
    name: String(form.get("name") || "").trim() || autoName,
    operator: String(form.get("operator") || "").trim(),
    candidateSourceMode: String(form.get("candidateSourceMode") || "browser_export"),
    categories,
    categoryPoolItemId: String(form.get("categoryPoolItemId") || ""),
    targetQualified: Number(form.get("targetQualified")),
    queueSize: Number(form.get("queueSize")),
    filters,
  };
  try {
    const batch = await api("/api/batches", { method: "POST", body: JSON.stringify(payload) });
    state.selectedId = batch.id;
    localStorage.setItem("amazon-console-selected", batch.id);
    document.getElementById("batchDialog").close();
    event.currentTarget.reset();
    await refresh();
    toast("类目批次已创建，该类目已标记为已分配", "good");
  } catch (error) { toast(error.message, "bad"); }
});

document.getElementById("categoryPoolForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("categoryPoolInput");
  const submittedValue = input.value;
  const source = input.value.trim();
  const preview = state.categoryPreview;
  if (!source) return;
  if (preview.status !== "ready" || preview.source !== source) {
    scheduleCategoryPreview(true);
    return;
  }
  const selection = categoryRepositoryUI.buildImportSelection(preview.items, preview.selectedKeys);
  if (!selection.selectedKeys.length || state.categoryImportPending) return;
  state.categoryImportPending = true;
  renderCategoryImportPreview();
  try {
    const result = await api("/api/category-pool/import", {
      method: "POST",
      body: JSON.stringify({ categories: source, ...selection }),
    });
    const inputUnchanged = categoryRepositoryUI.shouldClearSubmittedInput(input.value, submittedValue);
    if (inputUnchanged) {
      input.value = "";
      clearCategoryPreview();
    }
    await refresh();
    if (!inputUnchanged) scheduleCategoryPreview(true);
    const summary = categoryRepositoryUI.importResultSummary(result);
    toast(summary.text, summary.tone);
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    state.categoryImportPending = false;
    renderCategoryImportPreview();
  }
});

document.getElementById("categoryPoolInput").addEventListener("input", () => scheduleCategoryPreview(false));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelector("dialog[open]")?.close();
});

refresh();
setInterval(refresh, 5000);
