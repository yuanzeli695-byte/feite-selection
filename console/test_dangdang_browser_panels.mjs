import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => readFileSync(join(root, relativePath), "utf8").replace(/\r\n/g, "\n");
const sha256 = (relativePath) => createHash("sha256").update(readFileSync(join(root, relativePath))).digest("hex").toUpperCase();
const manifest = JSON.parse(read("browser-panel-ui-package.json"));
const source = read(manifest.output);
const collectorOnlySource = read(manifest.collectorOnlyOutput);
const rightOnlySource = read(manifest.rightOnlyOutput);
const testSource = source.replace(
  /  start\(\);\n\}\)\(\);\n$/,
  `  globalThis.__dangdangBrowserPanelsTest = Object.freeze({
    ADAPTER_VERSION, UI_PACKAGE_VERSION, UI_CSS_SHA256, FEATURE_FLAG,
    DANGDANG_SCOPED_CSS, TARGETS, buttonVariant, ensurePackageBadge,
    upgradePanel, ensureStyle, upgradeAvailablePanels, attachDangDangPanelLayout
  });
})();
`,
);

assert.notEqual(testSource, source, "DangDang browser panel test hook was not injected");
const rightTestSource = rightOnlySource.replace(
  /  start\(\);\n\}\)\(\);\n$/,
  `  globalThis.__dangdangBrowserPanelsTest = Object.freeze({
    ADAPTER_VERSION, UI_PACKAGE_VERSION, UI_CSS_SHA256, FEATURE_FLAG,
    DANGDANG_SCOPED_CSS, TARGETS, buttonVariant, ensurePackageBadge,
    upgradePanel, ensureStyle, upgradeAvailablePanels, attachDangDangPanelLayout
  });
})();
`,
);
assert.notEqual(rightTestSource, rightOnlySource, "Right-only DangDang panel test hook was not injected");

function loadApi(overrides = {}) {
  const context = { globalThis: null, Set, ...overrides };
  context.globalThis = context;
  vm.runInNewContext(testSource, context, { filename: manifest.output });
  return context.__dangdangBrowserPanelsTest;
}

function loadRightApi(overrides = {}) {
  const context = { globalThis: null, Set, ...overrides };
  context.globalThis = context;
  vm.runInNewContext(rightTestSource, context, { filename: manifest.rightOnlyOutput });
  return context.__dangdangBrowserPanelsTest;
}

function fakeClassList(initial = []) {
  const values = new Set(initial);
  return {
    add(...items) { items.forEach((item) => values.add(item)); },
    contains(item) { return values.has(item); },
    values() { return [...values]; },
    replaceAll(items) {
      values.clear();
      String(items || "").split(/\s+/).filter(Boolean).forEach((item) => values.add(item));
    },
  };
}

function fakeNode({ id = "", tagName = "div", classes = [] } = {}) {
  const classList = fakeClassList(classes);
  const attributes = new Map();
  const children = [];
  const node = {
    id,
    tagName: tagName.toUpperCase(),
    classList,
    attributes,
    children,
    title: "",
    textContent: "",
    appendChild(child) { children.push(child); return child; },
    insertBefore(child, before) {
      const index = children.indexOf(before);
      if (index < 0) children.push(child);
      else children.splice(index, 0, child);
      return child;
    },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    querySelector() { return null; },
  };
  Object.defineProperty(node, "className", {
    get() { return classList.values().join(" "); },
    set(value) { classList.replaceAll(value); },
  });
  return node;
}

function fakePanel(kind) {
  const isRunner = kind === "runner";
  const isBridge = kind === "bridge";
  const buttonIds = isRunner
    ? ["ss-v3-toggle", "ss-v3-generate", "ss-v3-start", "ss-v3-pause", "ss-v3-excel", "ss-v3-delete-done"]
    : isBridge
      ? ["asc-v2-pair"]
      : ["ss-collector-check", "ss-collector-run", "ss-collector-copy-json"];
  const buttons = buttonIds.map((id) => fakeNode({ id, tagName: "button", classes: id === "ss-v3-start" ? ["ss-v3-primary"] : [] }));
  buttons.forEach((button) => { button.listenerToken = `listener:${button.id}`; });
  const inputs = isRunner
    ? [fakeNode({ id: "ss-v3-name", tagName: "input" })]
    : isBridge
      ? [fakeNode({ id: "asc-v2-pairing", tagName: "input" })]
      : [];
  const selects = isRunner ? [fakeNode({ id: "ss-v3-picker", tagName: "select" })] : [];
  const textareas = isRunner
    ? [fakeNode({ id: "ss-v3-queue", tagName: "textarea" }), fakeNode({ id: "ss-v3-output", tagName: "textarea" })]
    : isBridge
      ? []
      : [fakeNode({ id: "ss-collector-json", tagName: "textarea" })];
  const statusNodes = isBridge ? [fakeNode({ id: "asc-v2-status", tagName: "span" })] : [];
  const metaNodes = isBridge ? [fakeNode({ tagName: "small" })] : [];
  inputs.forEach((input) => { input.value = "preserve-input-value"; });
  textareas.forEach((textarea) => { textarea.value = "preserve-textarea-value"; });
  const outputs = isBridge ? [] : [fakeNode({ id: isRunner ? "ss-v3-status" : "ss-collector-output", tagName: "pre" })];
  const heading = fakeNode({ tagName: isRunner ? "h3" : isBridge ? "strong" : "div" });
  if (isRunner) heading.children.push(buttons[0]);
  heading.querySelector = (selector) => selector === "button" && isRunner ? buttons[0] : null;
  const panel = fakeNode({ id: isRunner ? "ss-v3-panel" : isBridge ? "asc-v2-panel" : "ss-collector-panel" });
  heading.textContent = isRunner
    ? "卖家精灵一体化选品 0.3.8.13"
    : isBridge
      ? "Selection Console Bridge 2.1.3 / script 2.1.6"
      : "卖家精灵流量采集器 0.4.6.4";
  panel.textContent = heading.textContent;
  panel.firstElementChild = heading;
  panel.ownerDocument = { createElement: (tagName) => fakeNode({ tagName }) };
  panel.querySelectorAll = (selector) => ({ button: buttons, input: inputs, select: selects, textarea: textareas, pre: outputs, span: statusNodes, small: metaNodes }[selector] || []);
  panel.querySelector = (selector) => {
    if (selector === "h3") return isRunner ? heading : null;
    if (selector === "[data-dd-ui-badge]") {
      return heading.children.find((child) => child.getAttribute("data-dd-ui-badge")) || null;
    }
    if (selector.startsWith("[data-dd-ui-badge=")) {
      return heading.children.find((child) => child.getAttribute("data-dd-ui-badge") === manifest.adapterVersion) || null;
    }
    return null;
  };
  return { panel, heading, buttons, inputs, selects, textareas, outputs };
}

function layoutFixture() {
  const listeners = new Map();
  const storage = new Map();
  const addListener = (type, handler) => {
    const handlers = listeners.get(type) || new Set();
    handlers.add(handler);
    listeners.set(type, handlers);
  };
  const removeListener = (type, handler) => listeners.get(type)?.delete(handler);
  const fire = (type, event = {}) => {
    for (const handler of [...(listeners.get(type) || [])]) handler({
      pointerId: 1,
      clientX: 0,
      clientY: 0,
      button: 0,
      isPrimary: true,
      preventDefault() {},
      ...event,
    });
  };
  const styleValues = new Map();
  const style = {
    setProperty(name, value) { styleValues.set(name, String(value)); },
    removeProperty(name) { styleValues.delete(name); },
  };
  const makeTarget = (tagName = "div") => {
    const targetListeners = new Map();
    const target = {
      tagName: tagName.toUpperCase(),
      classList: fakeClassList(),
      attributes: new Map(),
      parentNode: null,
      addEventListener(type, handler) {
        const handlers = targetListeners.get(type) || new Set();
        handlers.add(handler);
        targetListeners.set(type, handlers);
      },
      removeEventListener(type, handler) { targetListeners.get(type)?.delete(handler); },
      fire(type, event = {}) {
        for (const handler of [...(targetListeners.get(type) || [])]) handler({
          pointerId: 1,
          clientX: 0,
          clientY: 0,
          button: 0,
          isPrimary: true,
          target,
          preventDefault() {},
          ...event,
        });
      },
      setAttribute(name, value) { target.attributes.set(name, String(value)); },
      getAttribute(name) { return target.attributes.get(name) ?? null; },
      removeAttribute(name) { target.attributes.delete(name); },
      setPointerCapture() {},
      releasePointerCapture() {},
    };
    Object.defineProperty(target, "className", {
      get() { return target.classList.values().join(" "); },
      set(value) { target.classList.replaceAll(value); },
    });
    return target;
  };
  const heading = makeTarget("div");
  const button = makeTarget("button");
  button.parentNode = heading;
  heading.children = [button];
  const panel = makeTarget("div");
  panel.id = "ss-collector-panel";
  panel.style = style;
  panel.children = [heading];
  panel.firstElementChild = heading;
  heading.parentNode = panel;
  panel.appendChild = (child) => {
    child.parentNode = panel;
    panel.children.push(child);
    return child;
  };
  panel.querySelector = (selector) => selector.includes("data-dd-layout-resize-handle")
    ? panel.children.find((child) => child.getAttribute("data-dd-layout-resize-handle") === "true") || null
    : null;
  panel.getBoundingClientRect = () => ({
    left: Number(styleValues.get("--dd-layout-left")) || 16,
    top: Number(styleValues.get("--dd-layout-top")) || 100,
    width: Number(styleValues.get("--dd-layout-width")) || 380,
    height: Number(styleValues.get("--dd-layout-height")) || 480,
  });
  const windowRef = {
    innerWidth: 1000,
    innerHeight: 800,
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, String(value)); },
      removeItem(key) { storage.delete(key); },
    },
    addEventListener: addListener,
    removeEventListener: removeListener,
    setTimeout(callback) { callback(); return 1; },
  };
  const documentRef = {
    defaultView: windowRef,
    documentElement: { clientWidth: 1000, clientHeight: 800 },
    createElement: (tagName) => makeTarget(tagName),
  };
  panel.ownerDocument = documentRef;
  return { panel, heading, button, windowRef, fire, storage, styleValues };
}

test("browser panel build is pinned to the supplied DangDang archive", () => {
  const packageJson = JSON.parse(read("package.json"));
  assert.equal(manifest.schemaVersion, "dangdangBrowserPanels/v1");
  assert.equal(manifest.package, "@dangdang/ui");
  assert.equal(manifest.packageVersion, "0.2.5");
  assert.equal(sha256(manifest.sourceArchive), manifest.sourceSha256);
  assert.equal(packageJson.scripts["build:browser-panel-ui"], "node frontend/build-dangdang-browser-panels.mjs");
  assert.match(packageJson.scripts["test:browser-panel-ui"], /test_dangdang_browser_panels\.mjs/);
  assert.equal(manifest.rightOnlyOutput, "static/dangdang-right-panels.user.js");
  assert.equal(manifest.rightOnlyInstallUrl, "http://127.0.0.1:8788/static/dangdang-right-panels.user.js");
  assert.equal(manifest.rightOnlyLayoutStorageKey, "amazon-selection-console:dangdang-right-layout:v1");
  assert.match(source, new RegExp(`@version\\s+${manifest.adapterVersion.replace(/\./g, "\\.")}`));
  assert.match(source, /const UI_PACKAGE_VERSION = "0\.2\.5"/);
  assert.match(source, /const FEATURE_FLAG = "ENABLE_DANGDANG_BROWSER_PANELS_V1"/);
  assert.match(source, /engineVersion: "0\.4\.6\.4"/);
  assert.match(source, /engineVersion: "0\.3\.8\.13"/);
  assert.match(source, /asc-v2-panel/);
  assert.match(source, /Selection Console Bridge 2\.1\.3 \/ script 2\.1\.6/);
  assert.match(source, /ENABLE_DANGDANG_BRIDGE_PANEL_V1/);
  assert.match(source, /ENABLE_DANGDANG_PANEL_LAYOUT_V1/);
  assert.match(source, /amazon-selection-console:dangdang-layout:v1/);
  assert.match(rightOnlySource, /@name\s+Amazon SellerSprite Right Panels - DangDang UI/);
  assert.match(rightOnlySource, new RegExp(`@version\\s+${manifest.adapterVersion.replace(/\./g, "\\.")}`));
  assert.match(rightOnlySource, /#asc-v2-panel/);
  assert.match(rightOnlySource, /amazon-selection-console:dangdang-right-layout:v1/);
  assert.match(rightOnlySource, /ENABLE_DANGDANG_RIGHT_PANEL_LAYOUT_V1/);
  assert.match(collectorOnlySource, /@name\s+Amazon SellerSprite Collector - DangDang UI/);
  assert.match(collectorOnlySource, /const FEATURE_FLAG = "ENABLE_DANGDANG_COLLECTOR_PANEL_V1"/);
  assert.match(collectorOnlySource, /const PANEL_ID = "ss-collector-panel"/);
  assert.match(collectorOnlySource, /const ENGINE_VERSION = "0\.4\.6\.4"/);
  assert.doesNotMatch(collectorOnlySource, /ss-v3-panel|0\.3\.8\.13|ss-v3-|asc-v2-panel|Selection Console Bridge|2\.1\.3|2\.1\.6/);
  assert.doesNotMatch(rightOnlySource, /ss-collector-panel|ss-collector-|0\.4\.6\.4/);
});

test("generated CSS is namespaced and excludes document-wide package rules", () => {
  const api = loadApi();
  assert.match(api.DANGDANG_SCOPED_CSS, /#ss-collector-panel\.dd-ui/);
  assert.match(api.DANGDANG_SCOPED_CSS, /#ss-v3-panel\.dd-ui/);
  assert.match(api.DANGDANG_SCOPED_CSS, /#asc-v2-panel\.dd-ui/);
  assert.match(api.DANGDANG_SCOPED_CSS, /\.dd-button/);
  assert.match(api.DANGDANG_SCOPED_CSS, /\.dd-textarea/);
  assert.match(api.DANGDANG_SCOPED_CSS, /\.dd-badge/);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /:root\b/);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /@keyframes\s+dd-spin\b/);
  assert.match(api.DANGDANG_SCOPED_CSS, /@keyframes\s+dd-browser-panels-v1-spin\b/);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /::-webkit-scrollbar/);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /(^|[},])\s*(body|html)(?=[\s.#:[>+~,{])/m);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /@import\b|url\s*\(|https?:\/\//);
  const digest = createHash("sha256").update(api.DANGDANG_SCOPED_CSS).digest("hex").toUpperCase();
  assert.equal(digest, api.UI_CSS_SHA256);
  const rightApi = loadRightApi();
  assert.match(rightApi.DANGDANG_SCOPED_CSS, /#ss-v3-panel\.dd-ui/);
  assert.match(rightApi.DANGDANG_SCOPED_CSS, /#asc-v2-panel\.dd-ui/);
  assert.match(
    rightApi.DANGDANG_SCOPED_CSS,
    /data-dd-layout-resize-handle="true"\]\s*\{[^}]*bottom:\s*10px;[^}]*width:\s*24px;[^}]*height:\s*24px;[^}]*linear-gradient/s,
  );
  assert.doesNotMatch(rightApi.DANGDANG_SCOPED_CSS, /#ss-collector-panel/);
  assert.doesNotMatch(rightApi.DANGDANG_SCOPED_CSS, /#asc-bridge-panel|#asc-ss-panel/);
  const rightDigest = createHash("sha256").update(rightApi.DANGDANG_SCOPED_CSS).digest("hex").toUpperCase();
  assert.equal(rightDigest, rightApi.UI_CSS_SHA256);
});

test("adapter is visual-only and has no workflow or network authority", () => {
  for (const forbidden of [
    /GM_/, /sessionStorage/, /fetch\s*\(/, /XMLHttpRequest/, /WebSocket/,
    /\.click\s*\(/, /dispatchEvent\s*\(/, /strict-qualified-history/, /sellerSpriteIntegratedBatch/,
  ]) {
    assert.doesNotMatch(source, forbidden);
  }
  assert.match(source, /localStorage/);
  assert.match(source, /amazon-selection-console:dangdang-layout:v1/);
  assert.match(source, /@grant\s+none/);
  assert.match(source, /if \(!ENABLE_DANGDANG_BROWSER_PANELS_V1\) return/);
  assert.match(source, /#asc-v2-panel\.dd-browser-panel/);
});

test("right-only adapter is visual-only and isolated from Collector", () => {
  for (const forbidden of [
    /GM_/, /sessionStorage/, /fetch\s*\(/, /XMLHttpRequest/, /WebSocket/,
    /\.click\s*\(/, /dispatchEvent\s*\(/, /strict-qualified-history/, /sellerSpriteIntegratedBatch/,
  ]) {
    assert.doesNotMatch(rightOnlySource, forbidden);
  }
  assert.match(rightOnlySource, /amazon-selection-console:dangdang-right-layout:v1/);
  assert.match(rightOnlySource, /ENABLE_DANGDANG_RIGHT_PANELS_V1/);
  assert.doesNotMatch(rightOnlySource, /#ss-collector-panel|ss-collector-|0\.4\.6\.4/);
  assert.doesNotMatch(rightOnlySource, /#asc-bridge-panel|#asc-ss-panel/);
  assert.match(rightOnlySource, /@grant\s+none/);
});

test("Collector-only output is scoped to the left panel", () => {
  assert.match(collectorOnlySource, /#ss-collector-panel\.dd-ui/);
  assert.doesNotMatch(collectorOnlySource, /#ss-v3-panel|ss-v3-|0\.3\.8\.13|#asc-v2-panel|asc-v2-|Selection Console Bridge/);
  assert.doesNotMatch(collectorOnlySource, /GM_|sessionStorage|fetch\s*\(|XMLHttpRequest|WebSocket|\.click\s*\(|dispatchEvent\s*\(/);
  assert.match(collectorOnlySource, /localStorage/);
  assert.match(collectorOnlySource, /amazon-selection-console:dangdang-layout:v1/);
  assert.match(collectorOnlySource, /@grant\s+none/);
  assert.match(collectorOnlySource, /ss-collector-run/);
  assert.match(collectorOnlySource, /ENABLE_DANGDANG_COLLECTOR_PANEL_V1/);
});

test("Collector upgrade preserves ids, values, and listener identity", () => {
  const api = loadApi();
  const fixture = fakePanel("collector");
  const idsBefore = fixture.buttons.map((button) => button.id);
  const listenersBefore = fixture.buttons.map((button) => button.listenerToken);
  const valuesBefore = fixture.textareas.map((textarea) => textarea.value);
  assert.equal(api.upgradePanel(fixture.panel, "collector"), true);
  assert.deepEqual(fixture.buttons.map((button) => button.id), idsBefore);
  assert.deepEqual(fixture.buttons.map((button) => button.listenerToken), listenersBefore);
  assert.deepEqual(fixture.textareas.map((textarea) => textarea.value), valuesBefore);
  assert.equal(fixture.panel.getAttribute("data-dd-ui-package"), "dangdang-ui-0.2.5");
  assert.equal(fixture.panel.getAttribute("data-dd-ui-adapter"), manifest.adapterVersion);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-collector-run").classList.contains("dd-button--primary"), true);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-collector-check").classList.contains("dd-button--secondary"), true);
  assert.equal(fixture.heading.children.filter((child) => child.getAttribute("data-dd-ui-badge") === manifest.adapterVersion).length, 1);
  api.upgradePanel(fixture.panel, "collector");
  assert.equal(fixture.heading.children.filter((child) => child.getAttribute("data-dd-ui-badge") === manifest.adapterVersion).length, 1);
});

test("adapter waits for the expected engine heading and repairs stale style", () => {
  const api = loadApi();
  const fixture = fakePanel("runner");
  fixture.heading.textContent = "卖家精灵一体化选品 0.3.8.12";
  fixture.panel.textContent = fixture.heading.textContent;
  assert.equal(api.upgradePanel(fixture.panel, "runner"), false);
  assert.equal(fixture.panel.classList.contains("dd-ui"), false);

  const styles = [];
  const staleStyle = fakeNode({ tagName: "style" });
  staleStyle.id = "dd-browser-panels-v1-style";
  staleStyle.textContent = "stale";
  staleStyle.setAttribute("data-dd-ui-adapter", "0.0.1");
  const document = {
    getElementById: () => staleStyle,
    createElement: (tagName) => fakeNode({ tagName }),
    head: { appendChild: (node) => styles.push(node) },
    documentElement: { appendChild: (node) => styles.push(node) },
  };
  const apiWithDocument = loadApi({ document });
  const repaired = apiWithDocument.ensureStyle();
  assert.equal(repaired, staleStyle);
  assert.equal(repaired.textContent, apiWithDocument.DANGDANG_SCOPED_CSS);
  assert.equal(repaired.getAttribute("data-dd-ui-adapter"), manifest.adapterVersion);
  assert.equal(styles.length, 0);
});

test("layout controller drags, resizes, clamps, persists, and resets without touching controls", () => {
  const api = loadApi();
  const fixture = layoutFixture();
  const controller = api.attachDangDangPanelLayout(fixture.panel, {
    enabled: true,
    key: "collector",
    kind: "collector",
    heading: fixture.heading,
    featureFlag: "ENABLE_DANGDANG_PANEL_LAYOUT_V1",
    storageKey: "amazon-selection-console:dangdang-layout:v1",
    defaults: { width: 380, minWidth: 280, maxWidth: 720, minHeight: 180, maxHeight: 600 },
  });
  assert.ok(controller);
  assert.equal(fixture.panel.getAttribute("data-dd-layout-enabled"), "true");
  assert.equal(fixture.panel.children.filter((child) => child.getAttribute("data-dd-layout-resize-handle") === "true").length, 1);

  fixture.heading.fire("pointerdown", { target: fixture.button, clientX: 100, clientY: 120 });
  assert.deepEqual(controller.getGeometry(), null);
  fixture.heading.fire("pointerdown", { target: fixture.heading, clientX: 100, clientY: 120 });
  fixture.fire("pointercancel", { clientX: 200, clientY: 220 });
  assert.deepEqual(controller.getGeometry(), null);
  assert.equal(fixture.panel.getAttribute("data-dd-layout-mode"), "default");
  assert.equal(fixture.storage.has("amazon-selection-console:dangdang-layout:v1"), false);
  fixture.heading.fire("pointerdown", { target: fixture.heading, clientX: 100, clientY: 120 });
  fixture.fire("pointermove", { clientX: 1100, clientY: 1000 });
  fixture.fire("pointerup", { clientX: 1100, clientY: 1000 });
  const moved = controller.getGeometry();
  assert.equal(moved.left, 612);
  assert.equal(moved.top, 312);
  assert.equal(fixture.panel.getAttribute("data-dd-layout-mode"), "free");

  const handle = fixture.panel.children.find((child) => child.getAttribute("data-dd-layout-resize-handle") === "true");
  handle.fire("pointerdown", { target: handle, clientX: 1000, clientY: 800 });
  fixture.fire("pointermove", { clientX: 0, clientY: 0 });
  fixture.fire("pointerup", { clientX: 0, clientY: 0 });
  const resized = controller.getGeometry();
  assert.equal(resized.width, 280);
  assert.equal(resized.height, 180);

  const saved = JSON.parse(fixture.storage.get("amazon-selection-console:dangdang-layout:v1"));
  assert.deepEqual(Object.keys(saved.panels.collector).sort(), ["height", "left", "top", "version", "width"]);
  fixture.heading.fire("dblclick", { target: fixture.heading });
  assert.equal(fixture.panel.getAttribute("data-dd-layout-mode"), "default");
  assert.equal(fixture.storage.has("amazon-selection-console:dangdang-layout:v1"), false);
});

test("right-only layout persists Bridge geometry under its isolated key", () => {
  const api = loadRightApi();
  const fixture = layoutFixture();
  fixture.panel.id = "asc-v2-panel";
  const controller = api.attachDangDangPanelLayout(fixture.panel, {
    enabled: true,
    key: "bridge",
    kind: "bridge",
    heading: fixture.heading,
    featureFlag: "ENABLE_DANGDANG_RIGHT_PANEL_LAYOUT_V1",
    storageKey: "amazon-selection-console:dangdang-right-layout:v1",
    defaults: { width: 300, minWidth: 220, maxWidth: 520, minHeight: 180, maxHeight: 900 },
  });
  assert.ok(controller);
  fixture.heading.fire("pointerdown", { target: fixture.heading, clientX: 100, clientY: 120 });
  fixture.fire("pointerup", { clientX: 120, clientY: 140 });
  const saved = JSON.parse(fixture.storage.get("amazon-selection-console:dangdang-right-layout:v1"));
  assert.deepEqual(Object.keys(saved.panels.bridge).sort(), ["height", "left", "top", "version", "width"]);
  assert.equal(fixture.storage.has("amazon-selection-console:dangdang-layout:v1"), false);
});

test("Runner upgrade preserves native controls and maps command variants", () => {
  const api = loadApi();
  const fixture = fakePanel("runner");
  const idsBefore = [...fixture.buttons, ...fixture.inputs, ...fixture.selects, ...fixture.textareas].map((node) => node.id);
  const inputValue = fixture.inputs[0].value;
  const textareaValues = fixture.textareas.map((textarea) => textarea.value);
  api.upgradePanel(fixture.panel, "runner");
  assert.deepEqual([...fixture.buttons, ...fixture.inputs, ...fixture.selects, ...fixture.textareas].map((node) => node.id), idsBefore);
  assert.equal(fixture.inputs[0].value, inputValue);
  assert.deepEqual(fixture.textareas.map((textarea) => textarea.value), textareaValues);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-v3-start").classList.contains("dd-button--primary"), true);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-v3-excel").classList.contains("dd-button--primary"), true);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-v3-delete-done").classList.contains("dd-button--danger"), true);
  assert.equal(fixture.buttons.find((button) => button.id === "ss-v3-toggle").classList.contains("dd-button--ghost"), true);
  assert.equal(fixture.inputs[0].classList.contains("dd-browser-panel__input"), true);
  assert.equal(fixture.selects[0].classList.contains("dd-browser-panel__select"), true);
  assert.equal(fixture.textareas.every((textarea) => textarea.classList.contains("dd-textarea")), true);
});

test("Bridge upgrade preserves the pairing contract and excludes the legacy v1 root", () => {
  const api = loadApi();
  const fixture = fakePanel("bridge");
  const idsBefore = [...fixture.buttons, ...fixture.inputs].map((node) => node.id);
  const valuesBefore = fixture.inputs.map((input) => input.value);
  const listenersBefore = fixture.buttons.map((button) => button.listenerToken);
  assert.equal(api.upgradePanel(fixture.panel, "bridge"), true);
  assert.deepEqual([...fixture.buttons, ...fixture.inputs].map((node) => node.id), idsBefore);
  assert.deepEqual(fixture.inputs.map((input) => input.value), valuesBefore);
  assert.deepEqual(fixture.buttons.map((button) => button.listenerToken), listenersBefore);
  assert.equal(fixture.panel.getAttribute("data-dd-ui-package"), "dangdang-ui-0.2.5");
  assert.equal(fixture.panel.getAttribute("data-dd-ui-bridge-feature"), "ENABLE_DANGDANG_BRIDGE_PANEL_V1");
  assert.equal(fixture.panel.getAttribute("data-dd-ui-adapter"), manifest.adapterVersion);
  assert.equal(fixture.buttons[0].classList.contains("dd-button--primary"), true);
  assert.equal(fixture.heading.children.filter((child) => child.getAttribute("data-dd-ui-badge") === manifest.adapterVersion).length, 1);
  assert.doesNotMatch(api.DANGDANG_SCOPED_CSS, /#asc-bridge-panel/);
});

test("right-only Bridge upgrade preserves the same pairing controls", () => {
  const api = loadRightApi();
  const fixture = fakePanel("bridge");
  const idsBefore = [...fixture.buttons, ...fixture.inputs].map((node) => node.id);
  const valuesBefore = fixture.inputs.map((input) => input.value);
  const listenersBefore = fixture.buttons.map((button) => button.listenerToken);
  assert.equal(api.upgradePanel(fixture.panel, "bridge"), true);
  assert.deepEqual([...fixture.buttons, ...fixture.inputs].map((node) => node.id), idsBefore);
  assert.deepEqual(fixture.inputs.map((input) => input.value), valuesBefore);
  assert.deepEqual(fixture.buttons.map((button) => button.listenerToken), listenersBefore);
  assert.equal(fixture.panel.getAttribute("data-dd-ui-package"), "dangdang-ui-0.2.5");
  assert.equal(fixture.panel.getAttribute("data-dd-ui-adapter"), manifest.adapterVersion);
  assert.equal(fixture.panel.getAttribute("data-dd-ui-bridge-feature"), "ENABLE_DANGDANG_BRIDGE_PANEL_V1");
});

test("Bridge and server engine contracts remain pinned", () => {
  const bridge = read("browser_bridge_v2.user.js");
  const server = read("server.py");
  assert.match(bridge, /querySelectorAll\("#ss-v3-panel"\)/);
  assert.match(bridge, /querySelectorAll\("#ss-collector-panel"\)/);
  assert.match(source, /TARGETS = Object\.freeze\(\[/);
  assert.match(source, /asc-v2-panel/);
  assert.match(source, /2\.1\.3/);
  assert.match(source, /2\.1\.6/);
  assert.match(bridge, /const COLLECTOR_VERSION = "0\.4\.6\.4"/);
  assert.match(bridge, /const RUNNER_VERSION = "0\.3\.8\.13"/);
  // Since 7f1a4b4 the server derives the approved versions from the protected
  // manifest instead of hard-coding them, so pin the derivation plus the values
  // that manifest actually carries.
  assert.match(server, /APPROVED_COLLECTOR_VERSION = _APPROVED_SCRIPTS\["versions"\]\["collector"\]/);
  assert.match(server, /APPROVED_RUNNER_VERSION = _APPROVED_SCRIPTS\["versions"\]\["runner"\]/);
  const protectedHashes = JSON.parse(read("../pipeline/config/protected_script_hashes.json"));
  assert.equal(protectedHashes.approvedPair.collector, "0.4.6.4");
  assert.equal(protectedHashes.approvedPair.runner, "0.3.8.13");
  assert.equal(protectedHashes.approvedPair.bridge, "2.1.3");
  assert.match(server, /BROWSER_PAIR_RELEASE_STATUS = "candidate_pending_live_smoke_and_paired30"/);
});
