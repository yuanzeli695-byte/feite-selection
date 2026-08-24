// ==UserScript==
// @name         Amazon SellerSprite Collector - DangDang UI
// @namespace    amazon-selection-console
// @version      __ADAPTER_VERSION__
// @description  DangDang UI adapter with visual-only layout controls for the existing Collector panel.
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
  const ENABLE_DANGDANG_COLLECTOR_PANEL_V1 = true;
  const ENABLE_DANGDANG_PANEL_LAYOUT_V1 = true;
  const DANGDANG_LAYOUT_FEATURE_FLAG = "__LAYOUT_FEATURE_FLAG__";
  const DANGDANG_LAYOUT_STORAGE_KEY = "__LAYOUT_STORAGE_KEY__";
  const STYLE_ID = "dd-collector-panel-v1-style";
  const PACKAGE_BADGE_ATTRIBUTE = "data-dd-ui-badge";
  const DANGDANG_SCOPED_CSS = __DANGDANG_SCOPED_CSS__;

  __DANGDANG_PANEL_LAYOUT_CONTROLLER__
  const PANEL_ID = "ss-collector-panel";
  const ENGINE_VERSION = "__COLLECTOR_VERSION__";
  const PRIMARY_BUTTON_IDS = new Set(["ss-collector-run"]);
  const PANEL_LAYOUT_DEFAULTS = Object.freeze({
    width: 380,
    minWidth: 280,
    maxWidth: 720,
    minHeight: 180,
    maxHeight: 1200,
  });

  function buttonVariant(button) {
    return PRIMARY_BUTTON_IDS.has(button.id) ? "dd-button--primary" : "dd-button--secondary";
  }

  function panelHeading(panel) {
    return panel.firstElementChild;
  }

  function panelIsReady(panel) {
    const heading = panelHeading(panel);
    return Boolean(
      heading
      && String(heading.textContent || "").includes(ENGINE_VERSION)
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

  function ensurePackageBadge(panel) {
    const existingBadge = panel.querySelector(`[${PACKAGE_BADGE_ATTRIBUTE}]`);
    if (existingBadge) return configurePackageBadge(existingBadge);
    const heading = panelHeading(panel);
    if (!heading) return;
    const badge = panel.ownerDocument.createElement("span");
    configurePackageBadge(badge);
    const headingButton = heading.querySelector ? heading.querySelector("button") : null;
    if (headingButton && heading.insertBefore) heading.insertBefore(badge, headingButton);
    else heading.appendChild(badge);
    return badge;
  }

  function upgradePanel(panel) {
    if (!panel || !panelIsReady(panel)) return false;
    panel.classList.add("dd-ui", "dd-theme-scope", "dd-browser-panel", "dd-browser-panel--collector");
    panel.setAttribute("data-dd-ui-package", `dangdang-ui-${UI_PACKAGE_VERSION}`);
    panel.setAttribute("data-dd-ui-adapter", ADAPTER_VERSION);
    panel.setAttribute("data-dd-ui-css-sha256", UI_CSS_SHA256);
    panel.setAttribute("data-dd-ui-feature", FEATURE_FLAG);
    panel.querySelectorAll("button").forEach((button) => {
      button.classList.add("dd-button", "dd-button--sm", buttonVariant(button));
    });
    panel.querySelectorAll("input").forEach((input) => input.classList.add("dd-browser-panel__input"));
    panel.querySelectorAll("select").forEach((select) => select.classList.add("dd-browser-panel__select"));
    panel.querySelectorAll("textarea").forEach((textarea) => {
      textarea.classList.add("dd-textarea", "dd-textarea--resize-vertical", "dd-browser-panel__textarea");
    });
    panel.querySelectorAll("pre").forEach((pre) => pre.classList.add("dd-browser-panel__output"));
    ensurePackageBadge(panel);
    if (ENABLE_DANGDANG_PANEL_LAYOUT_V1) {
      attachDangDangPanelLayout(panel, {
        enabled: true,
        key: "collector",
        kind: "collector",
        heading: panelHeading(panel),
        featureFlag: DANGDANG_LAYOUT_FEATURE_FLAG,
        storageKey: DANGDANG_LAYOUT_STORAGE_KEY,
        defaults: PANEL_LAYOUT_DEFAULTS,
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

  function upgradeAvailablePanel() {
    return upgradePanel(document.getElementById(PANEL_ID));
  }

  function boot() {
    if (!ENABLE_DANGDANG_COLLECTOR_PANEL_V1) return;
    ensureStyle();
    if (upgradeAvailablePanel()) return;
    let checks = 0;
    const timer = window.setInterval(() => {
      checks += 1;
      if (upgradeAvailablePanel() || checks >= 60) window.clearInterval(timer);
    }, 500);
  }

  function start() {
    if (!ENABLE_DANGDANG_COLLECTOR_PANEL_V1) return;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
    else boot();
  }

  start();
})();
