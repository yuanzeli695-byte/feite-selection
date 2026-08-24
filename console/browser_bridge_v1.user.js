// ==UserScript==
// @name         Amazon Selection Console Browser Bridge
// @namespace    amazon-selection-console
// @version      1.0.0
// @description  Local loopback bridge for the approved Collector/Runner pair.
// @match        https://www.amazon.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function () {
  "use strict";

  const API = "http://127.0.0.1:8788";
  const PROTOCOL = "browser-bridge-v1";
  const COLLECTOR_VERSION = "0.4.6";
  const RUNNER_VERSION = "0.3.7";
  const storageKey = "amazon-selection-console-bridge";
  const state = Object.assign({ batchId: "", token: "", queueHash: "", connected: false, lastCommand: "-" }, JSON.parse(localStorage.getItem(storageKey) || "{}"));

  function save() { localStorage.setItem(storageKey, JSON.stringify(state)); }
  function request(path, method, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url: API + path,
        headers: { "Content-Type": "application/json" },
        data: body ? JSON.stringify(body) : undefined,
        timeout: 10000,
        onload: (response) => {
          let payload = {};
          try { payload = JSON.parse(response.responseText || "{}"); } catch (_) { reject(new Error("bridge response is not JSON")); return; }
          if (response.status < 200 || response.status >= 300) { reject(new Error(payload.error || `HTTP ${response.status}`)); return; }
          resolve(payload);
        },
        onerror: () => reject(new Error("无法连接控制台，请确认 8788 端口已启动")),
        ontimeout: () => reject(new Error("控制台连接超时")),
      });
    });
  }

  function setStatus(text, good) {
    const node = document.querySelector("#asc-bridge-status");
    if (node) { node.textContent = text; node.dataset.good = good ? "1" : "0"; }
  }

  async function connect() {
    state.batchId = document.querySelector("#asc-bridge-batch").value.trim();
    state.token = document.querySelector("#asc-bridge-token").value.trim();
    state.queueHash = document.querySelector("#asc-bridge-queue").value.trim();
    if (!state.batchId || !state.token) throw new Error("请输入批次 ID 和 Bridge Token");
    await request("/bridge/register", "POST", { batchId: state.batchId, token: state.token, protocol: PROTOCOL, collectorVersion: COLLECTOR_VERSION, runnerVersion: RUNNER_VERSION, queueHash: state.queueHash });
    state.connected = true; save(); setStatus("已连接", true); await heartbeat();
  }

  async function heartbeat() {
    if (!state.connected) return;
    try {
      const payload = await request("/bridge/heartbeat", "POST", { batchId: state.batchId, token: state.token, protocol: PROTOCOL, collectorVersion: COLLECTOR_VERSION, runnerVersion: RUNNER_VERSION, state: window.__amazonSelectionRunnerState || "idle", stats: window.__amazonSelectionRunnerStats || {} });
      setStatus("已连接 · " + new Date().toLocaleTimeString(), true);
      (payload.commands || []).forEach(handleCommand);
    } catch (error) { state.connected = false; save(); setStatus(error.message, false); }
  }

  async function poll() {
    if (!state.connected) return;
      try { const payload = await request("/bridge/commands/poll", "POST", { batchId: state.batchId, token: state.token }); (payload.commands || []).forEach(handleCommand); } catch (_) { /* heartbeat reports connection errors */ }
  }

  async function handleCommand(command) {
    if (!command || command.id === state.lastCommand) return;
    state.lastCommand = command.id; save();
    window.postMessage({ source: "amazon-selection-console", type: "command", command }, "*");
    window.dispatchEvent(new CustomEvent("amazon-selection-console:command", { detail: command }));
    try { await request("/bridge/commands/ack", "POST", { batchId: state.batchId, token: state.token, commandId: command.id, status: "accepted" }); }
    catch (_) { /* next heartbeat will retry visibility */ }
  }

  async function sendEvent(detail) {
    if (!state.connected || !detail) return;
    try { await request("/bridge/event", "POST", Object.assign({ batchId: state.batchId, token: state.token, protocol: PROTOCOL }, detail)); } catch (error) { setStatus(error.message, false); }
  }

  window.addEventListener("amazon-selection-console:runner-state", (event) => sendEvent(event.detail));
  window.addEventListener("amazon-selection-console:artifact", (event) => {
    const detail = event.detail || {};
    sendEvent({ eventType: "artifact", artifact: detail });
    if (detail.path) request("/bridge/artifact", "POST", Object.assign({ batchId: state.batchId, token: state.token }, detail));
  });

  function mount() {
    if (document.getElementById("asc-bridge-panel")) return;
    const panel = document.createElement("aside"); panel.id = "asc-bridge-panel";
    panel.innerHTML = `<strong>Selection Console Bridge</strong><span id="asc-bridge-status" data-good="0">未连接</span><input id="asc-bridge-batch" placeholder="Batch ID"><input id="asc-bridge-token" type="password" placeholder="Bridge Token"><input id="asc-bridge-queue" placeholder="Queue hash (optional)"><button id="asc-bridge-connect">连接控制台</button><small>Collector ${COLLECTOR_VERSION} · Runner ${RUNNER_VERSION}</small>`;
    Object.assign(panel.style, { position: "fixed", right: "12px", bottom: "12px", zIndex: 2147483647, width: "250px", padding: "12px", background: "#fff", color: "#111", border: "1px solid #bbb", borderRadius: "6px", boxShadow: "0 4px 18px #0003", font: "12px Arial", display: "grid", gap: "6px" });
    document.body.appendChild(panel);
    panel.querySelectorAll("input").forEach((input) => { const key = input.id.replace("asc-bridge-", ""); input.value = state[key] || ""; });
    panel.querySelector("button").addEventListener("click", () => connect().catch((error) => setStatus(error.message, false)));
  }

  mount(); setInterval(heartbeat, 3000); setInterval(poll, 3000);
})();
