// ==UserScript==
// @name         Amazon SellerSprite Panels - DangDang UI
// @namespace    amazon-selection-console
// @version      0.3.1
// @description  DangDang UI adapter with visual-only panel layout controls for the existing Collector, Runner, and Selection Console Bridge panels.
// @match        https://www.amazon.com/*
// @match        https://amazon.com/*
// @downloadURL  http://127.0.0.1:8788/static/dangdang-browser-panels.user.js
// @updateURL    http://127.0.0.1:8788/static/dangdang-browser-panels.user.js
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const ADAPTER_VERSION = "0.3.1";
  const UI_PACKAGE_VERSION = "0.2.5";
  const UI_CSS_SHA256 = "DDFB206BBC5EF2ED693BCB758E7630ACF5E850DD66269183A49966BFC8D50061";
  const FEATURE_FLAG = "ENABLE_DANGDANG_BROWSER_PANELS_V1";
  const ENABLE_DANGDANG_BROWSER_PANELS_V1 = true;
  const ENABLE_DANGDANG_BRIDGE_PANEL_V1 = true;
  const ENABLE_DANGDANG_PANEL_LAYOUT_V1 = true;
  const DANGDANG_BRIDGE_FEATURE_FLAG = "ENABLE_DANGDANG_BRIDGE_PANEL_V1";
  const DANGDANG_BRIDGE_VERSION = "2.1.3";
  const DANGDANG_BRIDGE_SCRIPT_VERSION = "2.1.6";
  const DANGDANG_LAYOUT_FEATURE_FLAG = "ENABLE_DANGDANG_PANEL_LAYOUT_V1";
  const DANGDANG_LAYOUT_STORAGE_KEY = "amazon-selection-console:dangdang-layout:v1";
  const STYLE_ID = "dd-browser-panels-v1-style";
  const PACKAGE_BADGE_ATTRIBUTE = "data-dd-ui-badge";
  const DANGDANG_SCOPED_CSS = "/* Generated from @dangdang/ui 0.2.5; archive SHA-256 6AA0BBDD8AE7AADAAF29AAC57A5001C2D0A625105B6C1B2BB5621591D3DB15AA. */\n\n#ss-collector-panel.dd-ui,\n#ss-v3-panel.dd-ui,\n#asc-v2-panel.dd-ui {\n    --dd-color-accent: var(--app-theme-color, #18181b);\n    --dd-color-on-accent: var(--app-theme-contrast, #ffffff);\n    --dd-color-accent-dark: var(--app-theme-color-dark, #f4f4f5);\n    --dd-color-on-accent-dark: var(--app-theme-contrast-dark, #09090b);\n    --dd-radius-sm: 10px;\n    --dd-radius-md: 14px;\n    --dd-radius-lg: 20px;\n    --dd-radius-xl: 28px;\n    --dd-radius-full: 999px;\n    --dd-glass-blur: 22px;\n    --dd-glass-saturation: 1.35;\n    --dd-motion-fast: 170ms;\n    --dd-motion-normal: 220ms;\n    --dd-color-success: #15803d;\n    --dd-color-warning: #b45309;\n    --dd-color-error: #dc2626;\n    --dd-color-info: #2563eb;\n    --dd-z-modal: 50000;\n    --dd-z-toast: 70000;\n}\n\n.dd-ui,\n.dd-theme-scope,\n.dd-toast-viewport {\n    --dd-surface-canvas: #f4f4f5;\n    --dd-surface-raised: rgba(255, 255, 255, 0.92);\n    --dd-surface-glass: rgba(255, 255, 255, 0.72);\n    --dd-surface-muted: rgba(244, 244, 245, 0.88);\n    --dd-border-subtle: rgba(24, 24, 27, 0.1);\n    --dd-border-strong: rgba(24, 24, 27, 0.18);\n    --dd-text-primary: #18181b;\n    --dd-text-secondary: #71717a;\n    --dd-shadow-raised: 0 16px 42px rgba(24, 39, 75, 0.13);\n    --dd-shadow-modal: 0 28px 80px rgba(24, 24, 27, 0.2);\n    --dd-control-background: rgba(255, 255, 255, 0.86);\n    --dd-control-placeholder: #a1a1aa;\n    --dd-focus-ring: color-mix(in srgb, var(--dd-color-accent) 38%, transparent);\n    color: var(--dd-text-primary);\n}\n\n.dd-ui,\n.dd-ui *,\n.dd-ui *::before,\n.dd-ui *::after,\n.dd-theme-scope,\n.dd-theme-scope *,\n.dd-theme-scope *::before,\n.dd-theme-scope *::after,\n.dd-toast-viewport,\n.dd-toast-viewport *,\n.dd-toast-viewport *::before,\n.dd-toast-viewport *::after {\n    box-sizing: border-box;\n}\n\n.dd-ui--dark,\n.dd-theme-scope.dd-ui--dark,\n.dd-toast-viewport.dd-ui--dark {\n    --dd-surface-canvas: #09090b;\n    --dd-surface-raised: rgba(24, 24, 27, 0.92);\n    --dd-surface-glass: rgba(39, 39, 42, 0.72);\n    --dd-surface-muted: rgba(63, 63, 70, 0.82);\n    --dd-border-subtle: rgba(255, 255, 255, 0.12);\n    --dd-border-strong: rgba(255, 255, 255, 0.2);\n    --dd-text-primary: #f4f4f5;\n    --dd-text-secondary: #d4d4d8;\n    --dd-shadow-raised: 0 16px 42px rgba(0, 0, 0, 0.28);\n    --dd-shadow-modal: 0 28px 90px rgba(0, 0, 0, 0.5);\n    --dd-control-background: rgba(39, 39, 42, 0.82);\n    --dd-control-placeholder: #71717a;\n    --dd-focus-ring: color-mix(in srgb, var(--dd-color-accent-dark) 42%, transparent);\n}\n\n@media (prefers-reduced-motion: reduce) {\n    .dd-ui,\n    .dd-ui *,\n    .dd-ui *::before,\n    .dd-ui *::after,\n    .dd-theme-scope,\n    .dd-theme-scope *,\n    .dd-theme-scope *::before,\n    .dd-theme-scope *::after,\n    .dd-toast-viewport,\n    .dd-toast-viewport *,\n    .dd-toast-viewport *::before,\n    .dd-toast-viewport *::after {\n        scroll-behavior: auto !important;\n        transition-duration: 1ms !important;\n        animation-duration: 1ms !important;\n        animation-iteration-count: 1 !important;\n    }\n}\n\n\n.dd-button,\n.dd-icon-button {\n    box-sizing: border-box;\n    font: inherit;\n}\n\n.dd-button {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    gap: 8px;\n    border: 1px solid transparent;\n    border-radius: var(--dd-radius-md);\n    font-weight: 750;\n    line-height: 1;\n    cursor: pointer;\n    transition: background-color var(--dd-motion-fast) ease, border-color var(--dd-motion-fast) ease, color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease, transform var(--dd-motion-fast) ease;\n}\n\n.dd-button--sm { min-height: 34px; padding: 0 13px; font-size: 13px; }\n.dd-button--md { min-height: 42px; padding: 0 17px; font-size: 14px; }\n.dd-button--lg { min-height: 50px; padding: 0 22px; font-size: 15px; }\n.dd-button--full { width: 100%; }\n\n.dd-button--primary {\n    background: var(--dd-color-accent);\n    color: var(--dd-color-on-accent);\n    box-shadow: 0 10px 24px color-mix(in srgb, var(--dd-color-accent) 20%, transparent);\n}\n\n.dd-ui--dark .dd-button--primary,\n.dd-theme-scope.dd-ui--dark .dd-button--primary {\n    background: var(--dd-color-accent-dark);\n    color: var(--dd-color-on-accent-dark);\n}\n\n.dd-button--secondary {\n    background: var(--dd-surface-raised);\n    border-color: var(--dd-border-subtle);\n    color: var(--dd-text-primary);\n    box-shadow: var(--dd-shadow-raised);\n}\n\n.dd-button--ghost { background: transparent; color: var(--dd-text-primary); }\n.dd-button--danger { background: #dc2626; color: #ffffff; }\n.dd-button:not(:disabled):hover { transform: translateY(-1px); filter: brightness(0.98); }\n.dd-button:not(:disabled):active { transform: translateY(0) scale(0.99); }\n.dd-button:focus-visible,\n.dd-icon-button:focus-visible { outline: 3px solid var(--dd-focus-ring); outline-offset: 2px; }\n.dd-button:disabled,\n.dd-icon-button:disabled { cursor: not-allowed; opacity: 0.5; }\n\n.dd-button__spinner {\n    width: 15px;\n    height: 15px;\n    border: 2px solid currentColor;\n    border-right-color: transparent;\n    border-radius: 50%;\n    animation: dd-browser-panels-v1-spin 680ms linear infinite;\n}\n\n.dd-icon-button {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    flex: 0 0 auto;\n    border: 1px solid var(--dd-border-subtle);\n    border-radius: var(--dd-radius-full);\n    color: var(--dd-text-primary);\n    cursor: pointer;\n    transition: background-color var(--dd-motion-fast) ease, border-color var(--dd-motion-fast) ease, color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease;\n}\n\n.dd-icon-button--sm { width: 34px; height: 34px; }\n.dd-icon-button--md { width: 42px; height: 42px; }\n.dd-icon-button--lg { width: 52px; height: 52px; }\n.dd-icon-button--glass { background: var(--dd-surface-glass); box-shadow: var(--dd-shadow-raised); backdrop-filter: blur(var(--dd-glass-blur)) saturate(var(--dd-glass-saturation)); }\n.dd-icon-button--ghost { background: transparent; border-color: transparent; }\n.dd-icon-button--solid { background: var(--dd-color-accent); color: var(--dd-color-on-accent); }\n\n@keyframes dd-browser-panels-v1-spin { to { transform: rotate(360deg); } }\n\n@media (prefers-reduced-motion: reduce) {\n    .dd-button,\n    .dd-icon-button { animation-duration: 1ms !important; transition-duration: 1ms !important; }\n}\n\n\n.dd-form-field { display: grid; min-width: 0; gap: 9px; }\n.dd-form-field--horizontal { grid-template-columns: minmax(150px, .42fr) minmax(0, 1fr); align-items: start; column-gap: 24px; }\n.dd-form-field--horizontal .dd-form-field__message { grid-column: 2; }\n.dd-form-field__heading { min-width: 0; }\n.dd-form-field__label { display: flex; align-items: baseline; gap: 7px; color: var(--dd-text-primary); font-size: 13px; font-weight: 760; line-height: 1.35; }\n.dd-form-field__label > span { color: var(--dd-color-error); }\n.dd-form-field__label small { color: var(--dd-text-secondary); font-size: 10px; font-weight: 650; }\n.dd-form-field__description, .dd-form-field__message { margin: 5px 0 0; color: var(--dd-text-secondary); font-size: 11px; line-height: 1.5; }\n.dd-form-field__message { margin-top: -2px; }\n.dd-form-field__message--error { color: var(--dd-color-error); }\n.dd-form-field__control { min-width: 0; }\n\n.dd-input-shell, .dd-select-shell { display: inline-flex; min-width: 0; align-items: center; gap: 8px; border: 1px solid var(--dd-border-subtle); border-radius: var(--dd-radius-md); background: var(--dd-control-background); color: var(--dd-text-primary); box-shadow: inset 0 1px 0 rgba(255,255,255,.28); transition: border-color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease, background-color var(--dd-motion-fast) ease; }\n.dd-input-shell--full, .dd-select-shell { width: 100%; }\n.dd-input-shell--sm, .dd-select-shell--sm { min-height: 36px; padding: 0 11px; }\n.dd-input-shell--md, .dd-select-shell--md { min-height: 44px; padding: 0 13px; }\n.dd-input-shell--lg, .dd-select-shell--lg { min-height: 52px; padding: 0 15px; }\n.dd-input-shell:focus-within, .dd-select-shell:focus-within { border-color: color-mix(in srgb, var(--dd-color-accent) 55%, var(--dd-border-subtle)); box-shadow: 0 0 0 3px var(--dd-focus-ring); }\n.dd-ui--dark .dd-input-shell:focus-within, .dd-ui--dark .dd-select-shell:focus-within { border-color: color-mix(in srgb, var(--dd-color-accent-dark) 55%, var(--dd-border-subtle)); }\n.dd-input-shell--invalid, .dd-select-shell--invalid { border-color: color-mix(in srgb, var(--dd-color-error) 62%, var(--dd-border-subtle)); }\n.dd-input-shell--invalid:focus-within, .dd-select-shell--invalid:focus-within { box-shadow: 0 0 0 3px color-mix(in srgb, var(--dd-color-error) 22%, transparent); }\n.dd-input-shell--disabled, .dd-select-shell--disabled { cursor: not-allowed; opacity: .56; }\n.dd-input { width: 100%; min-width: 0; height: 100%; padding: 0; border: 0; outline: 0; background: transparent; color: inherit; font: inherit; font-size: 13px; }\n.dd-input::placeholder, .dd-textarea::placeholder { color: var(--dd-control-placeholder); }\n.dd-input__adornment { display: inline-flex; flex: 0 0 auto; align-items: center; color: var(--dd-text-secondary); }\n.dd-input__adornment svg { width: 17px; height: 17px; }\n\n.dd-textarea { display: block; width: 100%; min-height: 112px; padding: 13px 14px; border: 1px solid var(--dd-border-subtle); border-radius: var(--dd-radius-md); outline: 0; background: var(--dd-control-background); color: var(--dd-text-primary); font: inherit; font-size: 13px; line-height: 1.6; box-shadow: inset 0 1px 0 rgba(255,255,255,.24); transition: border-color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease; }\n.dd-textarea:focus { border-color: color-mix(in srgb, var(--dd-color-accent) 55%, var(--dd-border-subtle)); box-shadow: 0 0 0 3px var(--dd-focus-ring); }\n.dd-textarea--invalid { border-color: var(--dd-color-error); }\n.dd-textarea:disabled { cursor: not-allowed; opacity: .56; }\n.dd-textarea--resize-none { resize: none; }\n.dd-textarea--resize-horizontal { resize: horizontal; }\n.dd-textarea--resize-vertical { resize: vertical; }\n.dd-textarea--resize-both { resize: both; }\n\n.dd-select-shell { position: relative; padding-right: 38px; }\n.dd-select { width: 100%; min-width: 0; height: 100%; padding: 0; border: 0; outline: 0; appearance: none; background: transparent; color: inherit; font: inherit; font-size: 13px; cursor: pointer; }\n.dd-select:disabled { cursor: not-allowed; }\n.dd-select-shell > svg { position: absolute; right: 13px; width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; pointer-events: none; }\n\n.dd-choice { position: relative; display: inline-flex; align-items: flex-start; gap: 10px; color: var(--dd-text-primary); cursor: pointer; }\n.dd-choice > input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }\n.dd-choice__control { display: grid; width: 20px; height: 20px; flex: 0 0 20px; place-items: center; margin-top: 1px; border: 1px solid var(--dd-border-strong); background: var(--dd-control-background); transition: background-color var(--dd-motion-fast) ease, border-color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease, transform var(--dd-motion-fast) ease; }\n.dd-checkbox .dd-choice__control { border-radius: 6px; }\n.dd-radio .dd-choice__control { border-radius: 50%; }\n.dd-choice__control svg { width: 14px; height: 14px; fill: none; stroke: var(--dd-color-on-accent); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; opacity: 0; transform: scale(.6); transition: opacity var(--dd-motion-fast) ease, transform var(--dd-motion-fast) ease; }\n.dd-radio .dd-choice__control i { width: 8px; height: 8px; border-radius: 50%; background: var(--dd-color-on-accent); opacity: 0; transform: scale(.4); transition: opacity var(--dd-motion-fast) ease, transform var(--dd-motion-fast) ease; }\n.dd-choice > input:checked + .dd-choice__control, .dd-choice > input:indeterminate + .dd-choice__control { border-color: var(--dd-color-accent); background: var(--dd-color-accent); }\n.dd-ui--dark .dd-choice > input:checked + .dd-choice__control, .dd-ui--dark .dd-choice > input:indeterminate + .dd-choice__control { border-color: var(--dd-color-accent-dark); background: var(--dd-color-accent-dark); }\n.dd-ui--dark .dd-choice__control svg, .dd-ui--dark .dd-radio .dd-choice__control i { stroke: var(--dd-color-on-accent-dark); background: var(--dd-color-on-accent-dark); }\n.dd-choice > input:checked + .dd-choice__control svg, .dd-choice > input:indeterminate + .dd-choice__control svg, .dd-choice > input:checked + .dd-choice__control i { opacity: 1; transform: scale(1); }\n.dd-choice > input:focus-visible + .dd-choice__control { box-shadow: 0 0 0 3px var(--dd-focus-ring); }\n.dd-choice__copy { display: grid; gap: 3px; }\n.dd-choice__copy b { font-size: 13px; line-height: 1.35; }\n.dd-choice__copy small { color: var(--dd-text-secondary); font-size: 11px; line-height: 1.45; }\n.dd-choice--disabled { cursor: not-allowed; opacity: .5; }\n\n.dd-switch-field { display: inline-flex; align-items: center; justify-content: space-between; gap: 16px; color: var(--dd-text-primary); }\n.dd-switch-field__copy { display: grid; gap: 3px; }\n.dd-switch-field__copy b { font-size: 13px; }\n.dd-switch-field__copy small { color: var(--dd-text-secondary); font-size: 11px; line-height: 1.4; }\n.dd-switch { position: relative; display: inline-flex; flex: 0 0 auto; align-items: center; padding: 3px; border: 0; border-radius: 999px; background: color-mix(in srgb, var(--dd-text-secondary) 32%, transparent); cursor: pointer; transition: background-color var(--dd-motion-fast) ease, box-shadow var(--dd-motion-fast) ease; }\n.dd-switch--sm { width: 38px; height: 22px; }\n.dd-switch--md { width: 48px; height: 28px; }\n.dd-switch--lg { width: 58px; height: 34px; }\n.dd-switch--checked { background: var(--dd-color-accent); }\n.dd-ui--dark .dd-switch--checked { background: var(--dd-color-accent-dark); }\n.dd-switch:focus-visible { outline: 0; box-shadow: 0 0 0 3px var(--dd-focus-ring); }\n.dd-switch__thumb { width: calc(100% / 2 - 1px); aspect-ratio: 1; border-radius: 50%; background: #fff; box-shadow: 0 3px 9px rgba(24,24,27,.24); transform: translateX(0); transition: transform 220ms cubic-bezier(.18,1.12,.22,1); }\n.dd-switch--checked .dd-switch__thumb { transform: translateX(calc(100% + 2px)); }\n.dd-switch:disabled, .dd-switch-field--disabled { cursor: not-allowed; opacity: .5; }\n\n.dd-slider-field { display: grid; min-width: 0; gap: 10px; color: var(--dd-text-primary); }\n.dd-slider-field__heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }\n.dd-slider-field__heading label { font-size: 12px; font-weight: 750; }\n.dd-slider-field__heading output { color: var(--dd-text-secondary); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; }\n.dd-slider { width: 100%; height: 20px; margin: 0; appearance: none; background: transparent; cursor: pointer; }\n.dd-slider::-webkit-slider-runnable-track { height: 5px; border-radius: 999px; background: linear-gradient(90deg, var(--dd-color-accent) 0 var(--dd-slider-progress), var(--dd-surface-muted) var(--dd-slider-progress) 100%); box-shadow: inset 0 0 0 1px var(--dd-border-subtle); }\n.dd-ui--dark .dd-slider::-webkit-slider-runnable-track { background: linear-gradient(90deg, var(--dd-color-accent-dark) 0 var(--dd-slider-progress), var(--dd-surface-muted) var(--dd-slider-progress) 100%); }\n.dd-slider::-moz-range-track { height: 5px; border-radius: 999px; background: var(--dd-surface-muted); }\n.dd-slider::-moz-range-progress { height: 5px; border-radius: 999px; background: var(--dd-color-accent); }\n.dd-slider::-webkit-slider-thumb { width: 19px; height: 19px; margin-top: -7px; appearance: none; border: 3px solid var(--dd-surface-raised); border-radius: 50%; background: var(--dd-color-accent); box-shadow: 0 3px 10px rgba(24,24,27,.22); transition: transform var(--dd-motion-fast) ease; }\n.dd-ui--dark .dd-slider::-webkit-slider-thumb { background: var(--dd-color-accent-dark); }\n.dd-slider::-moz-range-thumb { width: 15px; height: 15px; border: 3px solid var(--dd-surface-raised); border-radius: 50%; background: var(--dd-color-accent); box-shadow: 0 3px 10px rgba(24,24,27,.22); }\n.dd-slider:hover::-webkit-slider-thumb { transform: scale(1.08); }\n.dd-slider:focus-visible { outline: 0; }\n.dd-slider:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--dd-focus-ring); }\n.dd-slider-field--disabled { opacity: .5; }\n.dd-slider-field--disabled .dd-slider { cursor: not-allowed; }\n.dd-slider__marks { position: relative; height: 16px; margin: -4px 8px 0; }\n.dd-slider__marks span { position: absolute; transform: translateX(-50%); color: var(--dd-text-secondary); font-size: 9px; white-space: nowrap; }\n\n@media (max-width: 640px) { .dd-form-field--horizontal { grid-template-columns: 1fr; } .dd-form-field--horizontal .dd-form-field__message { grid-column: auto; } }\n\n\n/* Visual-only adapter. Exact panel IDs preserve the Browser Bridge light-DOM contract. */\n#ss-collector-panel.dd-browser-panel {\n  --app-theme-color: #f97316;\n  --app-theme-contrast: #ffffff;\n  --app-theme-color-dark: #fdba74;\n  --app-theme-contrast-dark: #18181b;\n}\n\n#ss-v3-panel.dd-browser-panel {\n  --app-theme-color: #0f766e;\n  --app-theme-contrast: #ffffff;\n  --app-theme-color-dark: #5eead4;\n  --app-theme-contrast-dark: #18181b;\n}\n\n#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel {\n  max-width: calc(100vw - 24px) !important;\n  border: 1px solid var(--dd-border-subtle) !important;\n  border-top: 3px solid var(--dd-color-accent) !important;\n  border-radius: var(--dd-radius-md) !important;\n  background: var(--dd-surface-raised) !important;\n  color: var(--dd-text-primary) !important;\n  box-shadow: var(--dd-shadow-modal) !important;\n  font-family: Inter, \"Segoe UI\", Arial, sans-serif !important;\n  letter-spacing: 0 !important;\n  z-index: 2147483640 !important;\n  scrollbar-color: #a1a1aa transparent;\n  scrollbar-width: thin;\n}\n\n#ss-collector-panel.dd-browser-panel {\n  width: 380px !important;\n  max-height: min(480px, calc(100vh - 110px)) !important;\n  padding: 12px !important;\n}\n\n#ss-v3-panel.dd-browser-panel {\n  width: 430px !important;\n  max-height: calc(100vh - 24px) !important;\n  padding: 12px !important;\n}\n\n#ss-collector-panel.dd-browser-panel > div:first-child,\n#ss-v3-panel.dd-browser-panel h3 {\n  display: flex;\n  min-width: 0;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 7px;\n  margin: 0 0 9px !important;\n  color: var(--dd-text-primary) !important;\n  font-size: 14px !important;\n  font-weight: 780 !important;\n  line-height: 1.35 !important;\n  letter-spacing: 0 !important;\n}\n\n#ss-v3-panel.dd-browser-panel h3 #ss-v3-toggle {\n  margin: 0 0 0 auto !important;\n}\n\n#ss-collector-panel.dd-browser-panel .dd-badge.dd-browser-panel__package-badge,\n#ss-v3-panel.dd-browser-panel .dd-badge.dd-browser-panel__package-badge {\n  display: inline-flex;\n  flex: 0 0 auto;\n  min-height: 20px;\n  align-items: center;\n  justify-content: center;\n  padding: 0 7px;\n  border: 1px solid var(--dd-border-subtle);\n  border-radius: var(--dd-radius-full);\n  background: var(--dd-surface-muted);\n  color: var(--dd-text-secondary);\n  font-size: 9px;\n  font-weight: 760;\n  line-height: 1;\n  letter-spacing: 0;\n  white-space: nowrap;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button,\n#ss-v3-panel.dd-browser-panel button.dd-button {\n  min-height: 32px;\n  max-width: 100%;\n  margin: 6px 6px 2px 0;\n  padding: 6px 10px;\n  border-radius: var(--dd-radius-sm);\n  font-family: inherit;\n  font-size: 11px;\n  font-weight: 750;\n  line-height: 1.25;\n  letter-spacing: 0;\n  white-space: normal;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button--primary,\n#ss-v3-panel.dd-browser-panel button.dd-button--primary {\n  border-color: var(--dd-color-accent);\n  background: var(--dd-color-accent);\n  color: var(--dd-color-on-accent);\n  box-shadow: 0 7px 18px color-mix(in srgb, var(--dd-color-accent) 18%, transparent);\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button--secondary,\n#ss-v3-panel.dd-browser-panel button.dd-button--secondary {\n  border-color: var(--dd-border-subtle);\n  background: var(--dd-control-background);\n  color: var(--dd-text-primary);\n  box-shadow: inset 0 1px #ffffff47;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button--ghost,\n#ss-v3-panel.dd-browser-panel button.dd-button--ghost {\n  border-color: transparent;\n  background: transparent;\n  color: var(--dd-text-secondary);\n  box-shadow: none;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button--danger,\n#ss-v3-panel.dd-browser-panel button.dd-button--danger {\n  border-color: var(--dd-color-error);\n  background: var(--dd-color-error);\n  color: #ffffff;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button:disabled,\n#ss-v3-panel.dd-browser-panel button.dd-button:disabled {\n  cursor: not-allowed;\n  opacity: 0.48;\n  transform: none;\n}\n\n#ss-collector-panel.dd-browser-panel button.dd-button:focus-visible,\n#ss-v3-panel.dd-browser-panel button.dd-button:focus-visible {\n  outline: 3px solid var(--dd-focus-ring);\n  outline-offset: 2px;\n}\n\n#ss-v3-panel.dd-browser-panel label {\n  display: block;\n  margin-top: 8px;\n  color: var(--dd-text-primary);\n  font-size: 11px;\n  font-weight: 760;\n  line-height: 1.35;\n  letter-spacing: 0;\n}\n\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__input,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__select,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__textarea {\n  width: 100%;\n  min-width: 0;\n  border: 1px solid var(--dd-border-subtle) !important;\n  border-radius: var(--dd-radius-sm) !important;\n  outline: 0;\n  background: var(--dd-control-background) !important;\n  color: var(--dd-text-primary) !important;\n  box-shadow: inset 0 1px #ffffff47;\n  font-family: Consolas, \"Cascadia Mono\", monospace !important;\n  font-size: 11px !important;\n  line-height: 1.45 !important;\n  letter-spacing: 0 !important;\n}\n\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__input,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__select {\n  min-height: 34px;\n  padding: 6px 9px !important;\n}\n\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__textarea {\n  min-height: 92px;\n  padding: 9px 10px !important;\n  resize: vertical;\n}\n\n#ss-collector-panel.dd-browser-panel #ss-collector-json.dd-textarea {\n  display: none !important;\n}\n\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__input:focus,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__select:focus,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__textarea:focus {\n  border-color: color-mix(in srgb, var(--dd-color-accent) 55%, var(--dd-border-subtle)) !important;\n  box-shadow: 0 0 0 3px var(--dd-focus-ring);\n}\n\n#ss-collector-panel.dd-browser-panel #ss-collector-status,\n#ss-v3-panel.dd-browser-panel #ss-v3-message {\n  color: var(--dd-text-secondary) !important;\n  font-size: 11px !important;\n  line-height: 1.45;\n}\n\n#ss-v3-panel.dd-browser-panel #ss-v3-message {\n  font-weight: 720;\n}\n\n#ss-collector-panel.dd-browser-panel .dd-browser-panel__output,\n#ss-v3-panel.dd-browser-panel .dd-browser-panel__output {\n  overflow: auto;\n  border: 1px solid var(--dd-border-subtle) !important;\n  border-radius: var(--dd-radius-sm) !important;\n  background: var(--dd-surface-muted) !important;\n  color: var(--dd-text-primary);\n  box-shadow: inset 0 1px #ffffff47;\n  font-family: Consolas, \"Cascadia Mono\", monospace;\n  font-size: 10px !important;\n  line-height: 1.5;\n  letter-spacing: 0;\n  overflow-wrap: anywhere;\n  white-space: pre-wrap;\n}\n\n#ss-collector-panel.dd-browser-panel #ss-collector-output {\n  max-height: 250px;\n  margin: 8px 0 0;\n  padding: 9px;\n}\n\n#ss-v3-panel.dd-browser-panel #ss-v3-status {\n  max-height: 190px;\n  margin-top: 9px;\n  padding: 9px;\n}\n\n#ss-v3-panel.dd-browser-panel .ss-v3-divider {\n  margin: 11px 0 4px;\n  border: 0;\n  border-top: 1px solid var(--dd-border-subtle);\n}\n\n/* Bridge is a separate right-side panel; keep its pairing contract untouched. */\n#asc-v2-panel.dd-browser-panel {\n  --app-theme-color: #2563eb;\n  --app-theme-contrast: #ffffff;\n  --app-theme-color-dark: #93c5fd;\n  --app-theme-contrast-dark: #172554;\n  width: 300px !important;\n  max-width: calc(100vw - 24px) !important;\n  max-height: min(70vh, calc(100vh - 24px)) !important;\n  padding: 12px !important;\n  border: 1px solid var(--dd-border-subtle) !important;\n  border-top: 3px solid var(--dd-color-accent) !important;\n  border-radius: var(--dd-radius-md) !important;\n  background: var(--dd-surface-raised) !important;\n  color: var(--dd-text-primary) !important;\n  box-shadow: var(--dd-shadow-modal) !important;\n  font-family: Inter, \"Segoe UI\", Arial, sans-serif !important;\n  letter-spacing: 0 !important;\n  z-index: 2147483640 !important;\n  scrollbar-color: #a1a1aa transparent;\n  scrollbar-width: thin;\n}\n\n#asc-v2-panel.dd-browser-panel > strong {\n  display: flex;\n  min-width: 0;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 7px;\n  margin: 0 0 9px !important;\n  color: var(--dd-text-primary) !important;\n  font-size: 14px !important;\n  font-weight: 780 !important;\n  line-height: 1.35 !important;\n  letter-spacing: 0 !important;\n}\n\n#asc-v2-panel.dd-browser-panel .dd-badge.dd-browser-panel__package-badge {\n  display: inline-flex;\n  flex: 0 0 auto;\n  min-height: 20px;\n  align-items: center;\n  justify-content: center;\n  padding: 0 7px;\n  border: 1px solid var(--dd-border-subtle);\n  border-radius: var(--dd-radius-full);\n  background: var(--dd-surface-muted);\n  color: var(--dd-text-secondary);\n  font-size: 9px;\n  font-weight: 760;\n  line-height: 1;\n  letter-spacing: 0;\n  white-space: nowrap;\n}\n\n#asc-v2-panel.dd-browser-panel button.dd-button {\n  min-height: 32px;\n  max-width: 100%;\n  margin: 6px 6px 2px 0;\n  padding: 6px 10px;\n  border-radius: var(--dd-radius-sm);\n  font-family: inherit;\n  font-size: 11px;\n  font-weight: 750;\n  line-height: 1.25;\n  letter-spacing: 0;\n  white-space: normal;\n}\n\n#asc-v2-panel.dd-browser-panel button.dd-button--primary {\n  border-color: var(--dd-color-accent);\n  background: var(--dd-color-accent);\n  color: var(--dd-color-on-accent);\n  box-shadow: 0 7px 18px color-mix(in srgb, var(--dd-color-accent) 18%, transparent);\n}\n\n#asc-v2-panel.dd-browser-panel button.dd-button:disabled {\n  cursor: not-allowed;\n  opacity: 0.48;\n  transform: none;\n}\n\n#asc-v2-panel.dd-browser-panel button.dd-button:focus-visible,\n#asc-v2-panel.dd-browser-panel #asc-v2-pairing:focus-visible {\n  outline: 3px solid var(--dd-focus-ring);\n  outline-offset: 2px;\n}\n\n#asc-v2-panel.dd-browser-panel #asc-v2-pairing {\n  width: 100% !important;\n  min-width: 0;\n  min-height: 34px;\n  padding: 6px 9px !important;\n  border: 1px solid var(--dd-border-subtle) !important;\n  border-radius: var(--dd-radius-sm) !important;\n  outline: 0;\n  background: var(--dd-control-background) !important;\n  color: var(--dd-text-primary) !important;\n  box-shadow: inset 0 1px #ffffff47;\n  font-family: Consolas, \"Cascadia Mono\", monospace !important;\n  font-size: 11px !important;\n  line-height: 1.45 !important;\n  letter-spacing: 0 !important;\n}\n\n#asc-v2-panel.dd-browser-panel #asc-v2-status {\n  color: var(--dd-text-secondary) !important;\n  font-size: 11px !important;\n  line-height: 1.45;\n  overflow-wrap: anywhere;\n}\n\n#asc-v2-panel.dd-browser-panel #asc-v2-status[data-tone=\"good\"] {\n  color: var(--dd-color-success) !important;\n}\n\n#asc-v2-panel.dd-browser-panel #asc-v2-status[data-tone=\"bad\"] {\n  color: var(--dd-color-error) !important;\n}\n\n#asc-v2-panel.dd-browser-panel > small {\n  color: var(--dd-text-secondary) !important;\n  font-size: 10px !important;\n  line-height: 1.45;\n}\n\n@media (max-width: 700px) {\n  #ss-collector-panel.dd-browser-panel {\n    right: 8px !important;\n    bottom: 8px !important;\n    left: 8px !important;\n    width: auto !important;\n    max-height: 43vh !important;\n  }\n\n  #ss-v3-panel.dd-browser-panel {\n    top: 8px !important;\n    right: 8px !important;\n    left: 8px !important;\n    width: auto !important;\n    max-height: 50vh !important;\n  }\n\n  #asc-v2-panel.dd-browser-panel {\n    top: auto !important;\n    right: 8px !important;\n    bottom: 8px !important;\n    left: auto !important;\n    width: min(300px, calc(100vw - 16px)) !important;\n    max-height: 45vh !important;\n  }\n}\n\n\n/* Layout controls are scoped to roots that the adapter marks explicitly. */\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel)[data-dd-layout-enabled=\"true\"] {\n  overflow: auto !important;\n  resize: none !important;\n  box-sizing: border-box !important;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel)[data-dd-layout-mode=\"free\"] {\n  position: fixed !important;\n  top: var(--dd-layout-top) !important;\n  right: auto !important;\n  bottom: auto !important;\n  left: var(--dd-layout-left) !important;\n  width: var(--dd-layout-width) !important;\n  height: var(--dd-layout-height) !important;\n  z-index: var(--dd-layout-z-index, 2147483646) !important;\n  max-width: var(--dd-layout-max-width) !important;\n  max-height: var(--dd-layout-max-height) !important;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel)[data-dd-layout-dragging=\"true\"] {\n  user-select: none !important;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel) > [data-dd-layout-drag-handle=\"true\"] {\n  cursor: grab;\n  touch-action: none;\n  user-select: none;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel) > [data-dd-layout-drag-handle=\"true\"]:active,\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel)[data-dd-layout-dragging=\"true\"] > [data-dd-layout-drag-handle=\"true\"] {\n  cursor: grabbing;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel) > [data-dd-layout-resize-handle=\"true\"] {\n  position: absolute;\n  right: 8px;\n  bottom: 10px;\n  width: 24px;\n  height: 24px;\n  box-sizing: border-box;\n  z-index: 2;\n  cursor: nwse-resize;\n  touch-action: none;\n  user-select: none;\n  border: 1px solid color-mix(in srgb, var(--dd-text-secondary) 48%, transparent);\n  border-radius: 4px;\n  background:\n    linear-gradient(135deg, transparent 0 38%, color-mix(in srgb, var(--dd-text-secondary) 82%, transparent) 39% 46%, transparent 47% 58%, color-mix(in srgb, var(--dd-text-secondary) 82%, transparent) 59% 66%, transparent 67%),\n    color-mix(in srgb, var(--dd-surface-raised) 82%, transparent);\n  box-shadow: 0 1px 4px #0000002b;\n  opacity: 0.92;\n}\n\n:is(#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel)[data-dd-layout-resizing=\"true\"] > [data-dd-layout-resize-handle=\"true\"] {\n  opacity: 1;\n  border-color: var(--dd-color-accent);\n  box-shadow: 0 0 0 2px var(--dd-focus-ring), 0 1px 4px #00000038;\n}\n";

  const DANGDANG_LAYOUT_CONTROLLERS = new WeakMap();
let DANGDANG_LAYOUT_Z_INDEX = 2147483645;

function attachDangDangPanelLayout(panel, config) {
  if (!panel || !config || config.enabled === false) return null;

  const documentRef = panel.ownerDocument || (typeof document !== "undefined" ? document : null);
  const windowRef = documentRef?.defaultView || (typeof window !== "undefined" ? window : null);
  const heading = config.heading || (config.kind === "runner" ? panel.querySelector("h3") : panel.firstElementChild);
  if (!documentRef || !windowRef || !heading || !panel.style || typeof heading.addEventListener !== "function") return null;

  const existing = DANGDANG_LAYOUT_CONTROLLERS.get(panel);
  if (existing) {
    existing.refresh(heading);
    return existing;
  }

  const defaults = config.defaults || {};
  const storageKey = String(config.storageKey || "amazon-selection-console:dangdang-layout:v1");
  const panelKey = String(config.key || panel.id || "panel");
  const layoutFeature = String(config.featureFlag || "ENABLE_DANGDANG_PANEL_LAYOUT_V1");
  const allowedPanelKeys = new Set(["collector", "runner", "bridge"]);
  const margin = 8;
  const minWidth = Number(defaults.minWidth) || 280;
  const maxWidth = Number(defaults.maxWidth) || 720;
  const minHeight = Number(defaults.minHeight) || 160;
  const maxHeight = Number(defaults.maxHeight) || 1200;
  let currentHeading = null;
  let geometry = null;
  let initialized = false;
  let dragState = null;
  let resizeState = null;
  let resizeHandle = null;
  let saveTimer = null;

  function finite(value) {
    return Number.isFinite(Number(value));
  }

  function viewport() {
    const documentElement = documentRef.documentElement;
    return {
      width: Math.max(1, Number(windowRef.innerWidth) || Number(documentElement?.clientWidth) || 1280),
      height: Math.max(1, Number(windowRef.innerHeight) || Number(documentElement?.clientHeight) || 900),
    };
  }

  function bounds() {
    const size = viewport();
    const availableWidth = Math.max(180, size.width - margin * 2);
    const availableHeight = Math.max(120, size.height - margin * 2);
    const effectiveMinWidth = Math.min(minWidth, availableWidth);
    const effectiveMinHeight = Math.min(minHeight, availableHeight);
    return {
      minWidth: effectiveMinWidth,
      maxWidth: Math.max(effectiveMinWidth, Math.min(maxWidth, availableWidth)),
      minHeight: effectiveMinHeight,
      maxHeight: Math.max(effectiveMinHeight, Math.min(maxHeight, availableHeight)),
      viewport: size,
    };
  }

  function clampGeometry(next) {
    const limits = bounds();
    const width = Math.min(limits.maxWidth, Math.max(limits.minWidth, Number(next.width) || Number(defaults.width) || limits.minWidth));
    const height = Math.min(limits.maxHeight, Math.max(limits.minHeight, Number(next.height) || Number(defaults.height) || limits.minHeight));
    const visibleWidth = Math.min(width, Math.max(48, limits.viewport.width - margin * 2));
    const visibleHeight = Math.min(height, Math.max(48, limits.viewport.height - margin * 2));
    const maxLeft = Math.max(margin, limits.viewport.width - margin - visibleWidth);
    const maxTop = Math.max(margin, limits.viewport.height - margin - visibleHeight);
    const left = Math.min(maxLeft, Math.max(margin, Number(next.left) || margin));
    const top = Math.min(maxTop, Math.max(margin, Number(next.top) || margin));
    return { left: Math.round(left), top: Math.round(top), width: Math.round(width), height: Math.round(height) };
  }

  function readRect() {
    if (typeof panel.getBoundingClientRect === "function") {
      const rect = panel.getBoundingClientRect();
      if (rect && finite(rect.width) && finite(rect.height) && rect.width > 0 && rect.height > 0) {
        return {
          left: Number(rect.left) || 0,
          top: Number(rect.top) || 0,
          width: Number(rect.width),
          height: Number(rect.height),
        };
      }
    }
    return clampGeometry({
      left: defaults.left ?? margin,
      top: defaults.top ?? margin,
      width: defaults.width,
      height: defaults.height,
    });
  }

  function setVariable(name, value) {
    panel.style.setProperty(name, `${value}px`);
  }

  function removeVariable(name) {
    panel.style.removeProperty(name);
  }

  function setConstraintVariables() {
    const limits = bounds();
    setVariable("--dd-layout-min-width", limits.minWidth);
    setVariable("--dd-layout-max-width", limits.maxWidth);
    setVariable("--dd-layout-min-height", limits.minHeight);
    setVariable("--dd-layout-max-height", limits.maxHeight);
  }

  function applyGeometry(next) {
    geometry = clampGeometry(next);
    setConstraintVariables();
    setVariable("--dd-layout-left", geometry.left);
    setVariable("--dd-layout-top", geometry.top);
    setVariable("--dd-layout-width", geometry.width);
    setVariable("--dd-layout-height", geometry.height);
    panel.setAttribute("data-dd-layout-mode", "free");
    return geometry;
  }

  function safeStorage() {
    try {
      return windowRef.localStorage || null;
    } catch (_) {
      return null;
    }
  }

  function readStoredPanels() {
    const storage = safeStorage();
    if (!storage) return {};
    try {
      const parsed = JSON.parse(storage.getItem(storageKey) || "null");
      if (!parsed || parsed.schema !== "dangdangPanelLayout/v1" || !parsed.panels || typeof parsed.panels !== "object") return {};
      const panels = {};
      for (const key of allowedPanelKeys) {
        const candidate = parsed.panels[key];
        if (!candidate || candidate.version !== 1) continue;
        if (!["left", "top", "width", "height"].every((name) => finite(candidate[name]))) continue;
        panels[key] = {
          version: 1,
          left: Number(candidate.left),
          top: Number(candidate.top),
          width: Number(candidate.width),
          height: Number(candidate.height),
        };
      }
      return panels;
    } catch (_) {
      return {};
    }
  }

  function writeStoredPanels(panels) {
    const storage = safeStorage();
    if (!storage) return;
    try {
      const cleanPanels = {};
      for (const key of allowedPanelKeys) {
        const candidate = panels[key];
        if (!candidate || candidate.version !== 1) continue;
        if (!["left", "top", "width", "height"].every((name) => finite(candidate[name]))) continue;
        cleanPanels[key] = {
          version: 1,
          left: Number(candidate.left),
          top: Number(candidate.top),
          width: Number(candidate.width),
          height: Number(candidate.height),
        };
      }
      const keys = Object.keys(cleanPanels);
      if (!keys.length) {
        storage.removeItem(storageKey);
        return;
      }
      storage.setItem(storageKey, JSON.stringify({ schema: "dangdangPanelLayout/v1", panels: cleanPanels }));
    } catch (_) {
      // Layout is optional; private-mode storage failures must not affect the page.
    }
  }

  function storedGeometry() {
    const candidate = readStoredPanels()[panelKey];
    if (!candidate || candidate.version !== 1) return null;
    if (!["left", "top", "width", "height"].every((key) => finite(candidate[key]))) return null;
    return clampGeometry(candidate);
  }

  function persist() {
    if (!geometry) return;
    const panels = readStoredPanels();
    panels[panelKey] = { version: 1, ...geometry };
    writeStoredPanels(panels);
  }

  function persistSoon() {
    if (saveTimer != null) return;
    const schedule = typeof windowRef.setTimeout === "function" ? windowRef.setTimeout.bind(windowRef) : setTimeout;
    saveTimer = schedule(() => {
      saveTimer = null;
      persist();
    }, 120);
  }

  function clearPersistedLayout() {
    const panels = readStoredPanels();
    delete panels[panelKey];
    writeStoredPanels(panels);
  }

  function setActiveLayer() {
    DANGDANG_LAYOUT_Z_INDEX = Math.min(2147483647, DANGDANG_LAYOUT_Z_INDEX + 1);
    panel.style.setProperty("--dd-layout-z-index", String(DANGDANG_LAYOUT_Z_INDEX));
  }

  function restoreDefaultLayout() {
    geometry = null;
    panel.removeAttribute("data-dd-layout-mode");
    [
      "--dd-layout-left",
      "--dd-layout-top",
      "--dd-layout-width",
      "--dd-layout-height",
      "--dd-layout-z-index",
    ].forEach(removeVariable);
    setConstraintVariables();
    panel.setAttribute("data-dd-layout-mode", "default");
  }

  function isInteractiveTarget(target) {
    let node = target;
    while (node && node !== panel) {
      const tag = String(node.tagName || "").toLowerCase();
      if (["button", "input", "select", "textarea", "a", "option"].includes(tag)) return true;
      if (node.isContentEditable || node.getAttribute?.("contenteditable") === "true") return true;
      node = node.parentNode;
    }
    return false;
  }

  function removeDragListeners() {
    if (typeof windowRef.removeEventListener !== "function") return;
    windowRef.removeEventListener("pointermove", onPointerMove);
    windowRef.removeEventListener("pointerup", onPointerUp);
    windowRef.removeEventListener("pointercancel", onPointerCancel);
    windowRef.removeEventListener("keydown", onKeyDown);
  }

  function removeResizeListeners() {
    if (typeof windowRef.removeEventListener !== "function") return;
    windowRef.removeEventListener("pointermove", onResizeMove);
    windowRef.removeEventListener("pointerup", onResizeUp);
    windowRef.removeEventListener("pointercancel", onResizeCancel);
    windowRef.removeEventListener("keydown", onResizeKeyDown);
  }

  function finishDrag(commit) {
    if (!dragState) return;
    const state = dragState;
    dragState = null;
    removeDragListeners();
    panel.removeAttribute("data-dd-layout-dragging");
    if (!commit) {
      if (state.wasFree) applyGeometry(state.start);
      else restoreDefaultLayout();
    }
    else persist();
    if (panel.releasePointerCapture && state.pointerId != null) {
      try { panel.releasePointerCapture(state.pointerId); } catch (_) { /* pointer already released */ }
    }
  }

  function finishResize(commit) {
    if (!resizeState) return;
    const state = resizeState;
    resizeState = null;
    removeResizeListeners();
    panel.removeAttribute("data-dd-layout-resizing");
    if (!commit) {
      if (state.wasFree) applyGeometry(state.start);
      else restoreDefaultLayout();
    }
    else persist();
    if (resizeHandle?.releasePointerCapture && state.pointerId != null) {
      try { resizeHandle.releasePointerCapture(state.pointerId); } catch (_) { /* pointer already released */ }
    }
  }

  function onPointerMove(event) {
    if (!dragState || (event.pointerId != null && event.pointerId !== dragState.pointerId)) return;
    const dx = (Number(event.clientX) || 0) - dragState.startX;
    const dy = (Number(event.clientY) || 0) - dragState.startY;
    applyGeometry({ ...dragState.start, left: dragState.start.left + dx, top: dragState.start.top + dy });
    event.preventDefault?.();
  }

  function onPointerUp(event) {
    if (dragState && (event.pointerId == null || event.pointerId === dragState.pointerId)) finishDrag(true);
  }

  function onPointerCancel(event) {
    if (dragState && (event.pointerId == null || event.pointerId === dragState.pointerId)) finishDrag(false);
  }

  function onKeyDown(event) {
    if (dragState && event.key === "Escape") {
      event.preventDefault?.();
      finishDrag(false);
    }
  }

  function onResizeKeyDown(event) {
    if (resizeState && event.key === "Escape") {
      event.preventDefault?.();
      finishResize(false);
    }
  }

  function onPointerDown(event) {
    if (dragState || resizeState || isInteractiveTarget(event.target)) return;
    if (event.isPrimary === false) return;
    if (typeof event.button === "number" && event.button !== 0) return;
    const rect = readRect();
    const wasFree = panel.getAttribute("data-dd-layout-mode") === "free";
    const start = applyGeometry(rect);
    dragState = {
      pointerId: event.pointerId,
      startX: Number(event.clientX) || 0,
      startY: Number(event.clientY) || 0,
      start,
      wasFree,
    };
    panel.setAttribute("data-dd-layout-dragging", "true");
    setActiveLayer();
    event.preventDefault?.();
    if (panel.setPointerCapture && event.pointerId != null) {
      try { panel.setPointerCapture(event.pointerId); } catch (_) { /* capture is optional */ }
    }
    if (typeof windowRef.addEventListener === "function") {
      windowRef.addEventListener("pointermove", onPointerMove, { passive: false });
      windowRef.addEventListener("pointerup", onPointerUp, { passive: true });
      windowRef.addEventListener("pointercancel", onPointerCancel, { passive: true });
      windowRef.addEventListener("keydown", onKeyDown, { passive: false });
    }
  }

  function onResizePointerDown(event) {
    if (dragState || resizeState || event.isPrimary === false) return;
    if (typeof event.button === "number" && event.button !== 0) return;
    const rect = readRect();
    const wasFree = panel.getAttribute("data-dd-layout-mode") === "free";
    const start = applyGeometry(rect);
    resizeState = {
      pointerId: event.pointerId,
      startX: Number(event.clientX) || 0,
      startY: Number(event.clientY) || 0,
      start,
      wasFree,
    };
    panel.setAttribute("data-dd-layout-resizing", "true");
    setActiveLayer();
    event.preventDefault?.();
    if (resizeHandle?.setPointerCapture && event.pointerId != null) {
      try { resizeHandle.setPointerCapture(event.pointerId); } catch (_) { /* capture is optional */ }
    }
    if (typeof windowRef.addEventListener === "function") {
      windowRef.addEventListener("pointermove", onResizeMove, { passive: false });
      windowRef.addEventListener("pointerup", onResizeUp, { passive: true });
      windowRef.addEventListener("pointercancel", onResizeCancel, { passive: true });
      windowRef.addEventListener("keydown", onResizeKeyDown, { passive: false });
    }
  }

  function onResizeMove(event) {
    if (!resizeState || (event.pointerId != null && event.pointerId !== resizeState.pointerId)) return;
    const dx = (Number(event.clientX) || 0) - resizeState.startX;
    const dy = (Number(event.clientY) || 0) - resizeState.startY;
    applyGeometry({
      ...resizeState.start,
      width: resizeState.start.width + dx,
      height: resizeState.start.height + dy,
    });
    event.preventDefault?.();
  }

  function onResizeUp(event) {
    if (resizeState && (event.pointerId == null || event.pointerId === resizeState.pointerId)) finishResize(true);
  }

  function onResizeCancel(event) {
    if (resizeState && (event.pointerId == null || event.pointerId === resizeState.pointerId)) finishResize(false);
  }

  function onDoubleClick(event) {
    if (isInteractiveTarget(event.target)) return;
    event.preventDefault?.();
    finishDrag(false);
    finishResize(false);
    clearPersistedLayout();
    panel.removeAttribute("data-dd-layout-dragging");
    panel.removeAttribute("data-dd-layout-resizing");
    restoreDefaultLayout();
  }

  function onViewportResize() {
    const rect = readRect();
    if (panel.getAttribute("data-dd-layout-mode") === "free") {
      applyGeometry({ ...(geometry || rect), width: rect.width, height: rect.height });
      persistSoon();
    }
  }

  function bindHeading(nextHeading) {
    if (currentHeading === nextHeading) return;
    if (currentHeading?.removeEventListener) {
      currentHeading.removeEventListener("pointerdown", onPointerDown);
      currentHeading.removeEventListener("dblclick", onDoubleClick);
    }
    currentHeading = nextHeading;
    if (!currentHeading?.addEventListener) return;
    currentHeading.classList?.add("dd-browser-panel__drag-handle");
    currentHeading.setAttribute("data-dd-layout-drag-handle", "true");
    if (!currentHeading.getAttribute("title")) {
      currentHeading.setAttribute("title", "Drag to move; double-click to reset layout");
    }
    currentHeading.addEventListener("pointerdown", onPointerDown, { passive: false });
    currentHeading.addEventListener("dblclick", onDoubleClick, { passive: false });
  }

  function ensureResizeHandle() {
    if (resizeHandle && resizeHandle.parentNode === panel) return resizeHandle;
    const existingHandle = panel.querySelector?.("[data-dd-layout-resize-handle=\"true\"]");
    resizeHandle = existingHandle || documentRef.createElement("span");
    resizeHandle.classList?.add("dd-browser-panel__resize-handle");
    resizeHandle.setAttribute("data-dd-layout-resize-handle", "true");
    resizeHandle.setAttribute("role", "separator");
    resizeHandle.setAttribute("aria-label", "Resize panel");
    resizeHandle.setAttribute("title", "Drag to resize panel");
    if (!existingHandle) panel.appendChild(resizeHandle);
    if (!resizeHandle.__ddLayoutBound) {
      resizeHandle.addEventListener("pointerdown", onResizePointerDown, { passive: false });
      resizeHandle.__ddLayoutBound = true;
    }
    return resizeHandle;
  }

  function initialize() {
    if (initialized) return;
    initialized = true;
    panel.setAttribute("data-dd-layout-enabled", "true");
    panel.setAttribute("data-dd-layout-key", panelKey);
    panel.setAttribute("data-dd-layout-feature", layoutFeature);
    setConstraintVariables();
    ensureResizeHandle();
    const restored = storedGeometry();
    if (restored) {
      applyGeometry(restored);
      setActiveLayer();
    }
    else {
      panel.setAttribute("data-dd-layout-mode", "default");
    }
    if (typeof windowRef.addEventListener === "function") {
      windowRef.addEventListener("resize", onViewportResize, { passive: true });
    }
  }

  const controller = {
    refresh(nextHeading) {
      bindHeading(nextHeading || heading);
      initialize();
      return controller;
    },
    reset: onDoubleClick,
    getGeometry() { return geometry ? { ...geometry } : null; },
  };
  DANGDANG_LAYOUT_CONTROLLERS.set(panel, controller);
  controller.refresh(heading);
  return controller;
}


  const TARGETS = Object.freeze([
    Object.freeze({ panelId: "ss-collector-panel", kind: "collector", engineVersion: "0.4.6.4" }),
    Object.freeze({ panelId: "ss-v3-panel", kind: "runner", engineVersion: "0.3.8.13" }),
    Object.freeze({ panelId: "asc-v2-panel", kind: "bridge", headingText: "Selection Console Bridge 2.1.3 / script 2.1.6" }),
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
