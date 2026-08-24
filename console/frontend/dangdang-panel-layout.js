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
