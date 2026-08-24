import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("./sellersprite_browser_bridge_v1.user.js", import.meta.url), "utf8");
const testSource = source.replace(
  /  mount\(\);\r?\n  resumeActive\(\);\r?\n  setInterval\(poll, 2500\);\r?\n\}\)\(\);\r?\n$/,
  "  globalThis.__sellerSpriteBridgeTest = Object.freeze({ compactText, visibleExportChoiceDialog, immediateExportChoice, visibleExportSuccessDialog, visibleExportFailureMessage, unexpectedVisibleDialogMessage, currentExportSignal, submitExportWithConfirmation, state });\n})();\n",
);

assert.notEqual(testSource, source, "SellerSprite Bridge test hook was not injected");

function element(text, { visible = true, disabled = false, buttons = [] } = {}) {
  return {
    innerText: text,
    textContent: text,
    disabled,
    __visible: visible,
    getBoundingClientRect() { return visible ? { width: 100, height: 30 } : { width: 0, height: 0 }; },
    querySelectorAll(selector) { return selector === "button" ? buttons : []; },
    querySelector() { return null; },
  };
}

function loadBridge({ bodyText = "已登录", selectors = {}, navigations = [] } = {}) {
  const document = {
    body: element(bodyText),
    querySelectorAll(selector) {
      const value = selectors[selector];
      return typeof value === "function" ? value() : value || [];
    },
    querySelector() { return null; },
  };
  const context = {
    console,
    document,
    location: {
      pathname: "/v3/product-research",
      assign(url) { navigations.push(url); },
    },
    localStorage: { getItem() { return "{}"; }, setItem() {} },
    getComputedStyle(node) {
      return { display: node.__visible === false ? "none" : "block", visibility: "visible" };
    },
    setTimeout,
    clearTimeout,
    setInterval,
    URL,
    Date,
    JSON,
    Uint8Array,
  };
  context.globalThis = context;
  vm.runInNewContext(testSource, context, { filename: "sellersprite_browser_bridge_v1.user.js" });
  return context.__sellerSpriteBridgeTest;
}

test("SellerSprite Bridge is versioned and scoped to source pages", () => {
  assert.match(source, /@version\s+1\.0\.4/);
  assert.match(source, /@match\s+https:\/\/www\.sellersprite\.com\/v3\/product-research\*/);
  assert.match(source, /@match\s+https:\/\/www\.sellersprite\.com\/v2\/export-log\*/);
  assert.match(source, /@match\s+https:\/\/www\.sellersprite\.com\/w\/user\/login\*/);
  assert.match(source, /@updateURL\s+http:\/\/127\.0\.0\.1:8788\/seller-sprite-bridge\.user\.js/);
  assert.match(source, /@downloadURL\s+http:\/\/127\.0\.0\.1:8788\/seller-sprite-bridge\.user\.js/);
  assert.match(source, /@connect\s+o\.sellersprite\.com/);
  assert.match(source, /sellerSprite-bridge-v1\.0\.0/);
  assert.match(source, /SCRIPT_VERSION = "1\.0\.4"/);
  assert.match(source, /ENABLE_CONFIRMED_EXPORT_HANDSHAKE = true/);
});

test("Bridge preserves strict URL aliases and fail-closed upload flow", () => {
  assert.match(source, /minAmzUnit/);
  assert.match(source, /maxAmzUnit/);
  assert.match(source, /SellerSprite URL 放宽了严格条件/);
  assert.match(source, /contentBase64/);
  assert.match(source, /\/bridge\/sellersprite\/export/);
  assert.match(source, /generatedAfter/);
  assert.match(source, /20\\d\{2\}-\\d\{2\}-\\d\{2\}/);
  assert.match(source, /多个可下载文件，已停止避免错配/);
  assert.match(source, /EXPORT_WAIT_TIMEOUT_MS/);
  assert.match(source, /EXPORT_LOG_REFRESH_MS/);
  assert.match(source, /页面将自动刷新/);
  assert.match(source, /location\.reload\(\)/);
  assert.match(source, /location\.pathname\.includes\("\/v2\/export-log"\)/);
  assert.match(source, /const knownLinks =/);
  assert.match(source, /function hasResultRows\(\)/);
  assert.match(source, /\.asin-fba \.asin/);
  assert.match(source, /taskConfirmedAt/);
  assert.match(source, /数据导出中/);
  assert.match(source, /先只导出前/);
  assert.match(source, /旧版 Bridge 未确认 SellerSprite 导出任务/);
});

test("Bridge does not expose or persist third-party credentials", () => {
  assert.doesNotMatch(source, /api[_-]?key|cookie|secret\s*=/i);
  assert.match(source, /pairingToken/);
});

test("high-load export dialog selects immediate export and never appointment export", () => {
  const immediate = element("先只导出前1000条");
  const appointment = element("导出前1000条，并预约导出");
  const dialog = element("主人~ 导出负载过高，要爆啦！", { buttons: [immediate, appointment] });
  const bridge = loadBridge();
  assert.equal(bridge.immediateExportChoice(dialog), immediate);

  const appointmentOnly = element("主人~ 导出负载过高，要爆啦！", { buttons: [appointment] });
  assert.equal(bridge.immediateExportChoice(appointmentOnly), null);

  const duplicateImmediate = element("主人~ 导出负载过高，要爆啦！", { buttons: [immediate, element("先只导出前1,000条")] });
  assert.equal(bridge.immediateExportChoice(duplicateImmediate), null);

  const changedAmount = element("主人~ 导出负载过高，要爆啦！", { buttons: [element("先只导出前500条")] });
  assert.equal(bridge.immediateExportChoice(changedAmount), null);
});

test("export handshake only confirms the authoritative SellerSprite success dialog", () => {
  const success = element("数据导出中，需要1-5分钟... 请稍后在个人中心-我的导出中下载");
  const bridge = loadBridge({
    selectors: {
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": [success],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [success],
      ".export-by-need-dialog": [],
    },
  });
  assert.equal(bridge.currentExportSignal(true).kind, "confirmed");
});

test("export handshake reports a concrete SellerSprite rejection", () => {
  const failure = element("今日导出次数已用完，请明日再试");
  const bridge = loadBridge({
    selectors: {
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": [],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [failure],
      ".export-by-need-dialog": [],
    },
  });
  const signal = bridge.currentExportSignal(true);
  assert.equal(signal.kind, "failed");
  assert.match(signal.message, /今日导出次数已用完/);
});

test("hidden stale high-load dialogs are ignored", () => {
  const hiddenDialog = element("主人~ 导出负载过高，要爆啦！", { visible: false });
  const bridge = loadBridge({ selectors: { ".export-by-need-dialog": [hiddenDialog] } });
  assert.equal(bridge.visibleExportChoiceDialog(), null);
});

test("unknown visible export dialogs fail closed without choosing a generic confirm button", () => {
  const unknown = element("账户需要额外验证 确定");
  const bridge = loadBridge({
    selectors: {
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": [],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [],
      ".export-by-need-dialog": [],
      ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [unknown],
    },
  });
  const signal = bridge.currentExportSignal(true);
  assert.equal(signal.kind, "blocked");
  assert.match(signal.message, /账户需要额外验证/);
});

test("confirmed handshake clicks immediate export once, never appointment, then navigates", async () => {
  let phase = "idle";
  let mainClicks = 0;
  let immediateClicks = 0;
  let appointmentClicks = 0;
  const navigations = [];
  const immediate = element("先只导出前1000条");
  immediate.click = () => { immediateClicks += 1; phase = "success"; };
  const appointment = element("导出前1000条，并预约导出");
  appointment.click = () => { appointmentClicks += 1; };
  const choice = element("主人~ 导出负载过高，要爆啦！", { buttons: [immediate, appointment] });
  const success = element("数据导出中，需要1-5分钟 请稍后在个人中心-我的导出中下载");
  const selectors = {
    ".export-by-need-dialog": () => phase === "choice" ? [choice] : [],
    ".el-message-box__wrapper,.swal2-container,[role='dialog']": () => phase === "success" ? [success] : [],
    ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [],
    ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [],
  };
  const bridge = loadBridge({ selectors, navigations });
  const active = {};
  const button = { click() { mainClicks += 1; phase = "choice"; } };
  await bridge.submitExportWithConfirmation(active, button, "https://www.sellersprite.com/v3/product-research?market=US");
  assert.equal(mainClicks, 1);
  assert.equal(immediateClicks, 1);
  assert.equal(appointmentClicks, 0);
  assert.equal(active.phase, "wait_export_log");
  assert.match(active.taskConfirmedAt, /^20\d{2}-/);
  assert.deepEqual(navigations, ["https://www.sellersprite.com/v2/export-log"]);
});

test("direct authoritative success enters export-log only after confirmation", async () => {
  let phase = "idle";
  const navigations = [];
  const success = element("数据导出中，需要1-5分钟 请稍后在个人中心-我的导出中下载");
  const bridge = loadBridge({
    navigations,
    selectors: {
      ".export-by-need-dialog": [],
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": () => phase === "success" ? [success] : [],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [],
      ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [],
    },
  });
  const active = {};
  await bridge.submitExportWithConfirmation(active, { click() { phase = "success"; } }, "https://www.sellersprite.com/v3/product-research?market=US");
  assert.equal(active.phase, "wait_export_log");
  assert.ok(active.exportWaitStartedAt > 0);
  assert.match(active.taskConfirmedAt, /^20\d{2}-/);
  assert.deepEqual(navigations, ["https://www.sellersprite.com/v2/export-log"]);
});

test("SellerSprite rejection after click never navigates", async () => {
  let phase = "idle";
  const navigations = [];
  const failure = element("今日导出次数已用完，请明日再试");
  const bridge = loadBridge({
    navigations,
    selectors: {
      ".export-by-need-dialog": [],
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": [],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": () => phase === "failure" ? [failure] : [],
      ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [],
    },
  });
  await assert.rejects(
    bridge.submitExportWithConfirmation({}, { click() { phase = "failure"; } }, "https://www.sellersprite.com/v3/product-research?market=US"),
    /拒绝导出.*今日导出次数已用完/,
  );
  assert.deepEqual(navigations, []);
});

test("stale success dialog blocks a new export before clicking or navigating", async () => {
  let mainClicks = 0;
  const navigations = [];
  const stale = element("数据导出中，需要1-5分钟 请稍后在个人中心-我的导出中下载");
  const bridge = loadBridge({
    navigations,
    selectors: {
      ".export-by-need-dialog": [],
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": [stale],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": [],
      ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [],
    },
  });
  await assert.rejects(
    bridge.submitExportWithConfirmation({}, { click() { mainClicks += 1; } }, "https://www.sellersprite.com/v3/product-research?market=US"),
    /导出前存在未处理弹窗/,
  );
  assert.equal(mainClicks, 0);
  assert.deepEqual(navigations, []);
});

test("conflicting success and failure signals never navigate", async () => {
  let phase = "idle";
  const navigations = [];
  const success = element("数据导出中，需要1-5分钟 请稍后在个人中心-我的导出中下载");
  const failure = element("今日导出次数已用完，请明日再试");
  const bridge = loadBridge({
    navigations,
    selectors: {
      ".export-by-need-dialog": [],
      ".el-message-box__wrapper,.swal2-container,[role='dialog']": () => phase === "conflict" ? [success] : [],
      ".el-message--error,.el-notification--error,.el-message--warning,.el-notification--warning,.el-message-box__wrapper,.swal2-container,[role='alert']": () => phase === "conflict" ? [failure] : [],
      ".el-message-box__wrapper,.el-dialog__wrapper,.swal2-container,[role='dialog'],[role='alert']": [],
    },
  });
  await assert.rejects(
    bridge.submitExportWithConfirmation({}, { click() { phase = "conflict"; } }, "https://www.sellersprite.com/v3/product-research?market=US"),
    /回执互相冲突/,
  );
  assert.deepEqual(navigations, []);
});
