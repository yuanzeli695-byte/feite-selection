// ==UserScript==
// @name         Amazon Selection Console SellerSprite Bridge
// @namespace    amazon-selection-console
// @version      1.0.4
// @description  Execute strict SellerSprite browser-export jobs and return the original file to the local console.
// @updateURL    http://127.0.0.1:8788/seller-sprite-bridge.user.js
// @downloadURL  http://127.0.0.1:8788/seller-sprite-bridge.user.js
// @match        https://www.sellersprite.com/v3/product-research*
// @match        https://www.sellersprite.com/v2/export-log*
// @match        https://www.sellersprite.com/w/user/login*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @connect      www.sellersprite.com
// @connect      o.sellersprite.com
// ==/UserScript==

(function () {
  "use strict";

  const API = "http://127.0.0.1:8788";
  const BRIDGE_VERSION = "sellerSprite-bridge-v1.0.0";
  const SCRIPT_VERSION = "1.0.4";
  const ENABLE_CONFIRMED_EXPORT_HANDSHAKE = true;
  const EXPORT_DIALOG_TIMEOUT_MS = 15000;
  const EXPORT_SUBMIT_TIMEOUT_MS = 45000;
  const EXPORT_WAIT_TIMEOUT_MS = 10 * 60 * 1000;
  const EXPORT_LOG_REFRESH_MS = 10000;
  const STORAGE_KEY = "amazon-selection-console-sellersprite-bridge-v1";
  const state = Object.assign({ pairingToken: "", active: null, status: "未配对" }, loadState());

  function loadState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch (_) { return {}; }
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function request(path, method, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url: API + path,
        headers: { "Content-Type": "application/json" },
        data: body ? JSON.stringify(body) : undefined,
        timeout: 30000,
        onload: (response) => {
          let payload = {};
          try { payload = JSON.parse(response.responseText || "{}"); } catch (_) { reject(new Error("控制台响应不是 JSON")); return; }
          if (response.status < 200 || response.status >= 300) { reject(new Error(payload.error || `HTTP ${response.status}`)); return; }
          resolve(payload);
        },
        onerror: () => reject(new Error("无法连接 127.0.0.1:8788")),
        ontimeout: () => reject(new Error("控制台连接超时")),
      });
    });
  }

  function setStatus(message, tone) {
    state.status = message;
    saveState();
    const node = document.querySelector("#asc-ss-status");
    if (node) {
      node.textContent = message;
      node.dataset.tone = tone || "neutral";
    }
  }

  function visible(node) {
    if (!node) return false;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }

  function pageText() {
    return (document.body?.innerText || "").replace(/\s+/g, " ").trim();
  }

  function waitFor(predicate, timeoutMs = 30000, intervalMs = 500, timeoutMessage = "SellerSprite 页面等待超时") {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const check = () => {
        try {
          const value = predicate();
          if (value) { resolve(value); return; }
        } catch (error) { reject(error); return; }
        if (Date.now() - started >= timeoutMs) { reject(new Error(timeoutMessage)); return; }
        setTimeout(check, intervalMs);
      };
      check();
    });
  }

  function numberParam(params, names, label) {
    const values = names.flatMap((name) => params.getAll(name));
    if (values.length !== 1 || !Number.isFinite(Number(values[0]))) throw new Error(`SellerSprite URL 缺少严格字段 ${label}`);
    return Number(values[0]);
  }

  function validateStrictUrl(rawUrl, filters) {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:" || !/(^|\.)sellersprite\.com$/i.test(url.hostname)) throw new Error("SellerSprite URL 域名无效");
    const params = url.searchParams;
    if (params.get("market")?.toUpperCase() !== "US") throw new Error("SellerSprite URL 必须是 US 市场");
    const nodes = JSON.parse(params.get("nodeIdPaths") || "null");
    if (!Array.isArray(nodes) || !nodes.length || nodes.some((node) => !String(node).trim())) throw new Error("SellerSprite URL 缺少类目路径");
    const checks = [
      [numberParam(params, ["minPrice"], "minPrice") >= Number(filters.minPrice), "minPrice"],
      [numberParam(params, ["maxPrice"], "maxPrice") <= Number(filters.maxPrice), "maxPrice"],
      [numberParam(params, ["minReviewRating"], "minReviewRating") >= Number(filters.minRating), "minReviewRating"],
      [numberParam(params, ["minReviews"], "minReviews") >= Number(filters.minReviews), "minReviews"],
      [numberParam(params, ["maxReviews"], "maxReviews") <= Number(filters.maxReviews), "maxReviews"],
      [numberParam(params, ["minSales", "minAmzUnit"], "minSales") >= Number(filters.minChildSales), "minSales"],
      [numberParam(params, ["maxSales", "maxAmzUnit"], "maxSales") <= Number(filters.maxChildSales), "maxSales"],
      [numberParam(params, ["minVariations"], "minVariations") >= Number(filters.minVariations), "minVariations"],
      [numberParam(params, ["maxVariations"], "maxVariations") <= Number(filters.maxVariations), "maxVariations"],
      [numberParam(params, ["putawayMonth"], "putawayMonth") <= Number(filters.availableMonth), "putawayMonth"],
    ];
    const failed = checks.filter((item) => !item[0]).map((item) => item[1]);
    if (failed.length) throw new Error(`SellerSprite URL 放宽了严格条件: ${failed.join(", ")}`);
    return url.href;
  }

  function requireLogin() {
    const text = pageText();
    if (/未登录|游客|立即登录|用户登录/.test(text) || /\/w\/user\/login/.test(location.pathname)) {
      throw new Error("SellerSprite 登录已失效，请先在当前页面登录");
    }
  }

  function selectAllResults() {
    const selectors = [
      ".operate .left > label.el-checkbox",
      ".operate-warp .left > label.el-checkbox",
      ".operate .left input[type='checkbox']",
    ];
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (!node) continue;
      const input = node.matches("input") ? node : node.querySelector("input[type='checkbox']");
      if (input && !input.checked) (node.matches("input") ? node : node).click();
      return true;
    }
    return false;
  }

  function exportButton() {
    const button = document.querySelector("button.my-download");
    if (button) return button;
    return Array.from(document.querySelectorAll("button")).find((node) => visible(node) && /^导出$/.test((node.textContent || "").replace(/\s+/g, "").trim()));
  }

  function hasResultRows() {
    return document.querySelectorAll(".asin-fba .asin").length > 0;
  }

  function compactText(node) {
    return (node?.innerText || node?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function visibleExportChoiceDialog() {
    return Array.from(document.querySelectorAll(".export-by-need-dialog")).find(visible) || null;
  }

  function immediateExportChoice(dialog) {
    if (!dialog || !/导出负载过高/.test(compactText(dialog))) return null;
    const matches = Array.from(dialog.querySelectorAll("button")).filter((node) => {
      const label = compactText(node).replace(/\s+/g, "");
      return visible(node) && !node.disabled && /^先只导出前1,?000条$/.test(label);
    });
    return matches.length === 1 ? matches[0] : null;
  }

  function visibleExportSuccessDialog() {
    const selectors = ".el-message-box__wrapper,.swal2-container,[role='dialog']";
    return Array.from(document.querySelectorAll(selectors)).find((node) => {
      const text = compactText(node);
      return visible(node) && /数据导出中/.test(text) && /个人中心[^]*我的导出/.test(text);
    }) || null;
  }

  function visibleExportFailureMessage() {
    const selectors = ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']";
    const failure = Array.from(document.querySelectorAll(selectors)).find((node) => {
      const text = compactText(node);
      return visible(node) && /今日导出次数已用完|导出失败|导出异常|导出次数不足|无导出权限|权限不足|请求失败|系统繁忙|网络异常|请.*重试/.test(text);
    });
    return failure ? compactText(failure).slice(0, 300) : "";
  }

  function currentExportSignal(allowChoice) {
    requireLogin();
    const signals = [];
    const success = visibleExportSuccessDialog();
    if (success) signals.push({ kind: "confirmed", message: compactText(success) });
    const failure = visibleExportFailureMessage();
    if (failure) signals.push({ kind: "failed", message: failure });
    if (allowChoice) {
      const dialog = visibleExportChoiceDialog();
      if (dialog) signals.push({ kind: "choice", dialog, message: compactText(dialog) });
    }
    const unexpected = unexpectedVisibleDialogMessage();
    if (unexpected) signals.push({ kind: "blocked", message: unexpected });
    if (signals.length > 1) {
      return { kind: "ambiguous", message: signals.map((signal) => `${signal.kind}: ${signal.message || "无说明"}`).join(" | ") };
    }
    return signals[0] || null;
  }

  function unexpectedVisibleDialogMessage() {
    const selectors = ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']";
    const node = Array.from(document.querySelectorAll(selectors)).find((candidate) => {
      if (!visible(candidate)) return false;
      if (candidate.querySelector?.(".export-by-need-dialog")) return false;
      const text = compactText(candidate);
      if (!text || (/数据导出中/.test(text) && /我的导出/.test(text))) return false;
      return !/今日导出次数已用完|导出失败|导出异常|导出次数不足|无导出权限|权限不足|请求失败|系统繁忙|网络异常|请.*重试/.test(text);
    });
    return node ? compactText(node).slice(0, 300) : "";
  }

  function knownDownloadLinks() {
    return Array.from(document.querySelectorAll("a[href]"), (node) => node.href).filter((href) => /download|export|\.xlsx(?:$|\?)/i.test(href));
  }

  function generatedAfter(text, startedAt) {
    const stamp = String(text || "").match(/\b(20\d{2}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\b/);
    if (!stamp) return false;
    const rowAt = new Date(stamp[1].replace(" ", "T"));
    const startAt = new Date(startedAt);
    if (!Number.isFinite(rowAt.getTime()) || !Number.isFinite(startAt.getTime())) return false;
    // SellerSprite renders local time while exportStartedAt is ISO; allow a
    // short clock skew without admitting older export rows.
    return rowAt.getTime() >= startAt.getTime() - 2 * 60 * 1000;
  }

  function asBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + chunkSize)));
    return btoa(binary);
  }

  function downloadBinary(url) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: "GET",
        url,
        responseType: "arraybuffer",
        timeout: 120000,
        onload: (response) => {
          if (response.status < 200 || response.status >= 300 || !response.response) { reject(new Error(`SellerSprite 文件下载失败 HTTP ${response.status}`)); return; }
          const disposition = response.responseHeaders?.match?.(/content-disposition:[^\r\n]*filename\*?=(?:UTF-8''|\"?)([^\"\r\n;]+)/i)?.[1];
          resolve({ buffer: response.response, fileName: disposition ? decodeURIComponent(disposition.replace(/\"/g, "")) : "sellersprite_export.xlsx" });
        },
        onerror: () => reject(new Error("SellerSprite 导出文件下载失败")),
        ontimeout: () => reject(new Error("SellerSprite 导出文件下载超时")),
      });
    });
  }

  async function acknowledge(command, status, message) {
    await request("/bridge/sellersprite/ack", "POST", { pairingToken: state.pairingToken, batchId: command.batchId, commandId: command.id, status, message });
  }

  async function failActive(error) {
    const active = state.active;
    state.active = null;
    saveState();
    setStatus(error.message, "bad");
    if (active) await acknowledge(active.command, "failed", error.message).catch(() => {});
  }

  function primeExportState(active, queryUrl) {
    active.phase = "submit_export";
    active.queryUrl = queryUrl;
    active.exportStartedAt = new Date().toISOString();
    active.exportWaitStartedAt = 0;
    active.taskConfirmedAt = "";
    active.scriptVersion = SCRIPT_VERSION;
    saveState();
  }

  async function submitExportWithConfirmation(active, button, queryUrl) {
    const staleSignal = currentExportSignal(true);
    if (staleSignal) throw new Error(`SellerSprite 导出前存在未处理弹窗：${staleSignal.message || staleSignal.kind}`);
    primeExportState(active, queryUrl);
    button.click();
    let signal = await waitFor(
      () => currentExportSignal(true),
      EXPORT_DIALOG_TIMEOUT_MS,
      250,
      "SellerSprite 未显示导出确认或成功回执",
    );
    if (signal.kind === "failed") throw new Error(`SellerSprite 拒绝导出：${signal.message}`);
    if (signal.kind === "blocked") throw new Error(`SellerSprite 未确认导出任务：${signal.message}`);
    if (signal.kind === "ambiguous") throw new Error(`SellerSprite 导出回执互相冲突：${signal.message}`);
    if (signal.kind === "choice") {
      const immediate = immediateExportChoice(signal.dialog);
      if (!immediate) throw new Error("SellerSprite 导出确认弹窗已变化，未点击任何选项");
      immediate.click();
      signal = await waitFor(
        () => currentExportSignal(false),
        EXPORT_SUBMIT_TIMEOUT_MS,
        250,
        "SellerSprite 未确认导出任务已创建",
      );
      if (signal.kind === "failed") throw new Error(`SellerSprite 拒绝导出：${signal.message}`);
      if (signal.kind === "blocked") throw new Error(`SellerSprite 未确认导出任务：${signal.message}`);
      if (signal.kind === "ambiguous") throw new Error(`SellerSprite 导出回执互相冲突：${signal.message}`);
    }
    if (signal.kind !== "confirmed") throw new Error("SellerSprite 未确认导出任务已创建");
    active.phase = "wait_export_log";
    active.taskConfirmedAt = new Date().toISOString();
    active.exportWaitStartedAt = Date.now();
    saveState();
    setStatus("SellerSprite 已确认导出任务，等待文件生成", "neutral");
    if (location.pathname.includes("/v3/product-research")) location.assign("https://www.sellersprite.com/v2/export-log");
  }

  async function prepareResearchPage(active) {
    requireLogin();
    if (!location.pathname.includes("/v3/product-research")) throw new Error("SellerSprite 当前页面不是产品研究页");
    const queryUrl = validateStrictUrl(location.href, active.command.payload.filters || {});
    if (active.command.payload.nodeIdPath && !new URL(queryUrl).searchParams.get("nodeIdPaths")?.includes(active.command.payload.nodeIdPath)) throw new Error("SellerSprite 当前类目与批次不一致");
    await waitFor(
      () => document.querySelector(".operate-warp") && exportButton() && hasResultRows(),
      60000,
      500,
      "SellerSprite 查询结果等待超时",
    );
    requireLogin();
    if (!selectAllResults()) throw new Error("SellerSprite 未找到全选结果控件");
    await waitFor(
      () => {
        requireLogin();
        const current = exportButton();
        return current && !current.disabled ? current : null;
      },
      12000,
      500,
      "SellerSprite 导出按钮不可用，请检查账号权限或今日导出次数",
    );
    const button = exportButton();
    if (!button) throw new Error("SellerSprite 导出按钮在页面重绘后不可用");
    if (!ENABLE_CONFIRMED_EXPORT_HANDSHAKE) throw new Error("SellerSprite 自动导出确认已停用，请使用人工回退上传");
    await submitExportWithConfirmation(active, button, queryUrl);
  }

  function completedDownloadLink(active) {
    const links = Array.from(document.querySelectorAll("a[href]"))
      .filter((node) => visible(node) && /download|export|\.xlsx(?:$|\?)/i.test(node.href))
      .map((node) => ({ href: node.href, text: (node.closest("tr")?.textContent || node.textContent || "").replace(/\s+/g, " ").trim() }));
    const fresh = links.filter((item) => !(active.knownLinks || []).includes(item.href) && generatedAfter(item.text, active.exportStartedAt));
    const completed = fresh.filter((item) => /完成|成功|下载/.test(item.text));
    if (completed.length === 1) return completed[0];
    if (completed.length > 1) throw new Error("SellerSprite 导出记录存在多个可下载文件，已停止避免错配");
    if (fresh.length === 1) return fresh[0];
    return null;
  }

  async function finishExport(active) {
    requireLogin();
    if (!active.taskConfirmedAt) {
      throw new Error("旧版 Bridge 未确认 SellerSprite 导出任务，请更新后重试自动导出");
    }
    await waitFor(() => location.pathname.includes("/v2/export-log"), 20000);
    const link = completedDownloadLink(active);
    if (!link) {
      const waitStartedAt = Number(active.exportWaitStartedAt || Date.now());
      active.exportWaitStartedAt = waitStartedAt;
      if (Date.now() - waitStartedAt >= EXPORT_WAIT_TIMEOUT_MS) throw new Error("SellerSprite 导出记录等待超时");
      saveState();
      setStatus("等待 SellerSprite 导出完成，页面将自动刷新", "neutral");
      setTimeout(() => {
        if (state.active?.command?.id === active.command.id && state.active.phase === "wait_export_log") location.reload();
      }, EXPORT_LOG_REFRESH_MS);
      return;
    }
    const downloaded = await downloadBinary(link.href);
    const suffix = /\.(xlsx|csv|tsv)$/i.exec(downloaded.fileName)?.[1]?.toLowerCase();
    if (!suffix) throw new Error("SellerSprite 导出文件扩展名无效");
    setStatus("正在回传 SellerSprite 原始导出", "neutral");
    await request("/bridge/sellersprite/export", "POST", {
      pairingToken: state.pairingToken,
      batchId: active.command.batchId,
      batchToken: active.command.batchToken,
      commandId: active.command.id,
      categoryInput: active.command.payload.categoryInput,
      sourcePage: active.command.payload.sourcePage,
      queryUrl: active.queryUrl,
      capturedAt: active.exportStartedAt,
      fileName: downloaded.fileName,
      contentBase64: asBase64(downloaded.buffer),
    });
    state.active = null;
    saveState();
    setStatus("SellerSprite 导出已回传", "good");
  }

  async function resumeActive() {
    const active = state.active;
    if (!active) return;
    try {
      if (active.phase === "navigate") {
        active.phase = "research";
        saveState();
        location.assign(active.command.payload.queryUrl);
        return;
      }
      if (active.phase === "research") await prepareResearchPage(active);
      else if (active.phase === "submit_export") throw new Error("SellerSprite 导出提交确认被页面刷新中断，请重试自动导出");
      else if (active.phase === "wait_export_log") await finishExport(active);
    } catch (error) {
      await failActive(error);
    }
  }

  async function poll() {
    if (!state.pairingToken || state.active) return;
    try {
      const result = await request("/bridge/sellersprite/poll", "POST", { pairingToken: state.pairingToken });
      const command = (result.commands || [])[0];
      if (!command) { setStatus("已配对，等待导出命令", "good"); return; }
      if (command.action !== "seller_export" || !command.payload?.queryUrl) throw new Error("SellerSprite 导出命令格式无效");
      const knownLinks = location.pathname.includes("/v2/export-log") ? knownDownloadLinks() : [];
      state.active = { command, phase: "navigate", knownLinks };
      saveState();
      await acknowledge(command, "accepted", "SellerSprite Bridge 已接收导出命令");
      await resumeActive();
    } catch (error) {
      setStatus(error.message, "bad");
    }
  }

  function pair() {
    const value = document.querySelector("#asc-ss-pairing")?.value.trim();
    if (!value) { setStatus("请输入控制台配对码", "bad"); return; }
    state.pairingToken = value;
    saveState();
    setStatus("正在配对", "neutral");
    poll();
  }

  function mount() {
    if (document.querySelector("#asc-ss-panel")) return;
    const panel = document.createElement("aside");
    panel.id = "asc-ss-panel";
    panel.className = "notranslate";
    panel.innerHTML = `<strong>Selection Console · SellerSprite</strong><span id="asc-ss-status" data-tone="neutral">${state.status || "未配对"}</span><input id="asc-ss-pairing" type="password" placeholder="控制台配对码"><button id="asc-ss-pair" type="button">配对</button><small>${BRIDGE_VERSION} / script ${SCRIPT_VERSION} · 严格导出回传</small>`;
    Object.assign(panel.style, { position: "fixed", right: "12px", bottom: "12px", zIndex: 2147483647, width: "286px", padding: "12px", background: "#fff", color: "#161b1a", border: "1px solid #9ca3af", borderRadius: "6px", boxShadow: "0 8px 24px #0003", font: "12px Arial", display: "grid", gap: "7px" });
    document.body.appendChild(panel);
    const input = panel.querySelector("#asc-ss-pairing");
    input.value = state.pairingToken || "";
    input.style.cssText = "width:100%;padding:6px;border:1px solid #aaa;border-radius:3px";
    panel.querySelector("#asc-ss-pair").style.cssText = "padding:6px;border:1px solid #0b6b63;border-radius:3px;background:#0b6b63;color:#fff;cursor:pointer";
    panel.querySelector("#asc-ss-pair").addEventListener("click", pair);
  }

  mount();
  resumeActive();
  setInterval(poll, 2500);
})();
