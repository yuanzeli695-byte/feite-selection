// ==UserScript==
// @name         Amazon SellerSprite Panels - DangDang UI
// @namespace    amazon-selection-console
// @version      __ADAPTER_VERSION__
// @description  DangDang UI adapter with visual-only panel layout controls for the existing Collector, Runner, and Selection Console Bridge panels.
// @match        https://www.amazon.com/*
// @match        https://amazon.com/*
// @downloadURL  __INSTALL_URL__
// @updateURL    __INSTALL_URL__
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const ADAPTER_VERSION = "__ADAPTER_VERSION__";
  const UI_PACKAGE_VERSION = "__PACKAGE_VERSION__";
  const UI_CSS_SHA256 = "__SCOPED_CSS_SHA256__";
  const FEATURE_FLAG = "__FEATURE_FLAG__";
  const ENABLE_DANGDANG_BROWSER_PANELS_V1 = true;
  const ENABLE_DANGDANG_BRIDGE_PANEL_V1 = true;
  const ENABLE_DANGDANG_PANEL_LAYOUT_V1 = true;
  const DANGDANG_BRIDGE_FEATURE_FLAG = "__BRIDGE_FEATURE_FLAG__";
  const DANGDANG_BRIDGE_VERSION = "__BRIDGE_VERSION__";
  const DANGDANG_BRIDGE_SCRIPT_VERSION = "__BRIDGE_SCRIPT_VERSION__";
  const DANGDANG_LAYOUT_FEATURE_FLAG = "__LAYOUT_FEATURE_FLAG__";
  const DANGDANG_LAYOUT_STORAGE_KEY = "__LAYOUT_STORAGE_KEY__";
  const STYLE_ID = "dd-browser-panels-v1-style";
  const PACKAGE_BADGE_ATTRIBUTE = "data-dd-ui-badge";
  const DANGDANG_SCOPED_CSS = __DANGDANG_SCOPED_CSS__;

  __DANGDANG_PANEL_LAYOUT_CONTROLLER__

  const TARGETS = Object.freeze([
    Object.freeze({ panelId: "ss-collector-panel", kind: "collector", engineVersion: "__COLLECTOR_VERSION__" }),
    Object.freeze({ panelId: "ss-v3-panel", kind: "runner", engineVersion: "__RUNNER_VERSION__" }),
    Object.freeze({ panelId: "asc-v2-panel", kind: "bridge", headingText: "__BRIDGE_HEADING_TEXT__" }),
  ]);
  const PRIMARY_BUTTON_IDS = new Set(["ss-collector-run", "ss-v3-start", "ss-v3-excel", "asc-v2-pair"]);
  const DANGER_BUTTON_IDS = new Set(["ss-v3-delete-done"]);
  const GHOST_BUTTON_IDS = new Set(["ss-v3-toggle"]);
  const PANEL_LAYOUT_DEFAULTS = Object.freeze({
    collector: Object.freeze({ width: 380, minWidth: 280, maxWidth: 720, minHeight: 180, maxHeight: 1200 }),
    runner: Object.freeze({ width: 430, minWidth: 320, maxWidth: 760, minHeight: 220, maxHeight: 1400 }),
    bridge: Object.freeze({ width: 300, minWidth: 220, maxWidth: 520, minHeight: 180, maxHeight: 900 }),
  });

  function buttonVariant(button) {
    if (PRIMARY_BUTTON_IDS.has(button.id)) return "dd-button--primary";
    if (DANGER_BUTTON_IDS.has(button.id)) return "dd-button--danger";
    if (GHOST_BUTTON_IDS.has(button.id)) return "dd-button--ghost";
    return "dd-button--secondary";
  }

  function targetForKind(kind) {
    return TARGETS.find((target) => target.kind === kind);
  }

  function panelHeading(panel, kind) {
    return kind === "runner" ? panel.querySelector("h3") : panel.firstElementChild;
  }

  function panelIsReady(panel, kind) {
    const target = targetForKind(kind);
    const heading = target ? panelHeading(panel, kind) : null;
    const headingText = heading ? String(heading.textContent || "") : "";
    const expectedHeading = target?.headingText || target?.engineVersion || "";
    return Boolean(
      target
      && heading
      && headingText.includes(expectedHeading)
      && panel.querySelectorAll("button").length > 0,
    );
  }

  function configurePackageBadge(badge) {
    badge.className = "dd-badge dd-badge--sm dd-badge--neutral dd-browser-panel__package-badge";
    badge.setAttribute(PACKAGE_BADGE_ATTRIBUTE, ADAPTER_VERSION);
    badge.setAttribute("aria-label", `DangDang UI ${UI_PACKAGE_VERSION}`);
    badge.title = `Visual adapter ${ADAPTER_VERSION}; CSS SHA-256 ${UI_CSS_SHA256}`;
    badge.textContent = `DangDang UI ${UI_PACKAGE_VERSION}`;
    return badge;
  }

  function ensurePackageBadge(panel, kind) {
    const existingBadge = panel.querySelector(`[${PACKAGE_BADGE_ATTRIBUTE}]`);
    if (existingBadge) return configurePackageBadge(existingBadge);
    const heading = panelHeading(panel, kind);
    if (!heading) return;
    const badge = panel.ownerDocument.createElement("span");
    configurePackageBadge(badge);
    const headingButton = heading.querySelector ? heading.querySelector("button") : null;
    if (headingButton && heading.insertBefore) heading.insertBefore(badge, headingButton);
    else heading.appendChild(badge);
    return badge;
  }

  function upgradePanel(panel, kind) {
    if (!panel || !panelIsReady(panel, kind)) return false;
    panel.classList.add("dd-ui", "dd-theme-scope", "dd-browser-panel", `dd-browser-panel--${kind}`);
    panel.setAttribute("data-dd-ui-package", `dangdang-ui-${UI_PACKAGE_VERSION}`);
    panel.setAttribute("data-dd-ui-adapter", ADAPTER_VERSION);
    panel.setAttribute("data-dd-ui-css-sha256", UI_CSS_SHA256);
    panel.setAttribute("data-dd-ui-feature", FEATURE_FLAG);
    if (kind === "bridge") {
      panel.setAttribute("data-dd-ui-bridge-feature", DANGDANG_BRIDGE_FEATURE_FLAG);
      panel.setAttribute("data-dd-ui-bridge-version", DANGDANG_BRIDGE_VERSION);
      panel.setAttribute("data-dd-ui-bridge-script", DANGDANG_BRIDGE_SCRIPT_VERSION);
    }

    panel.querySelectorAll("button").forEach((button) => {
      button.classList.add("dd-button", "dd-button--sm", buttonVariant(button));
    });
    panel.querySelectorAll("input").forEach((input) => input.classList.add("dd-browser-panel__input"));
    panel.querySelectorAll("select").forEach((select) => select.classList.add("dd-browser-panel__select"));
    panel.querySelectorAll("textarea").forEach((textarea) => {
      textarea.classList.add("dd-textarea", "dd-textarea--resize-vertical", "dd-browser-panel__textarea");
    });
    panel.querySelectorAll("pre").forEach((pre) => pre.classList.add("dd-browser-panel__output"));
    if (kind === "bridge") {
      panel.querySelectorAll("span").forEach((span) => span.classList.add("dd-browser-panel__status"));
      panel.querySelectorAll("small").forEach((small) => small.classList.add("dd-browser-panel__meta"));
    }
    ensurePackageBadge(panel, kind);
    if (ENABLE_DANGDANG_PANEL_LAYOUT_V1 && (kind !== "bridge" || ENABLE_DANGDANG_BRIDGE_PANEL_V1)) {
      attachDangDangPanelLayout(panel, {
        enabled: true,
        key: kind,
        kind,
        heading: panelHeading(panel, kind),
        featureFlag: DANGDANG_LAYOUT_FEATURE_FLAG,
        storageKey: DANGDANG_LAYOUT_STORAGE_KEY,
        defaults: PANEL_LAYOUT_DEFAULTS[kind],
      });
    }
    return true;
  }

  function ensureStyle() {
    const current = document.getElementById(STYLE_ID);
    const style = current || document.createElement("style");
    style.id = STYLE_ID;
    style.setAttribute("data-dd-ui-adapter", ADAPTER_VERSION);
    style.setAttribute("data-dd-ui-package", UI_PACKAGE_VERSION);
    style.setAttribute("data-dd-ui-css-sha256", UI_CSS_SHA256);
    if (style.textContent !== DANGDANG_SCOPED_CSS) style.textContent = DANGDANG_SCOPED_CSS;
    if (!current) (document.head || document.documentElement).appendChild(style);
    return style;
  }

  function upgradeAvailablePanels() {
    let upgraded = 0;
    const activeTargets = TARGETS.filter((target) => target.kind !== "bridge" || ENABLE_DANGDANG_BRIDGE_PANEL_V1);
    activeTargets.forEach((target) => {
      if (upgradePanel(document.getElementById(target.panelId), target.kind)) upgraded += 1;
    });
    return { upgraded, total: activeTargets.length };
  }

  function boot() {
    if (!ENABLE_DANGDANG_BROWSER_PANELS_V1) return;
    ensureStyle();
    const initialProgress = upgradeAvailablePanels();
    if (initialProgress.upgraded === initialProgress.total) return;
    let checks = 0;
    const timer = window.setInterval(() => {
      checks += 1;
      const progress = upgradeAvailablePanels();
      if (progress.upgraded === progress.total || checks >= 60) window.clearInterval(timer);
    }, 500);
  }

  function start() {
    if (!ENABLE_DANGDANG_BROWSER_PANELS_V1) return;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
    else boot();
  }

  start();
})();
