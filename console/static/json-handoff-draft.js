(function initializeJsonHandoffDraft(root) {
  "use strict";

  const VERSION = "json-handoff-draft-v1.0.0";
  const ENABLED = true;

  function capture(editor, activeElement, drafts) {
    if (!ENABLED || !editor) return { batchId: "", sourceSha256: "", focused: false, selectionStart: 0, selectionEnd: 0, scrollTop: 0 };
    const batchId = String(editor.dataset?.batchId || "");
    const sourceSha256 = String(editor.dataset?.sourceSha256 || "");
    if (batchId && sourceSha256) drafts[batchId] = { sourceSha256, value: editor.value };
    return {
      batchId,
      sourceSha256,
      focused: editor === activeElement,
      selectionStart: Number(editor.selectionStart || 0),
      selectionEnd: Number(editor.selectionEnd || 0),
      scrollTop: Number(editor.scrollTop || 0),
    };
  }

  function valueFor(drafts, batchId, sourceSha256) {
    if (!ENABLED) return "";
    const draft = drafts[batchId];
    if (!draft) return "";
    if (!sourceSha256 || draft.sourceSha256 !== sourceSha256) {
      delete drafts[batchId];
      return "";
    }
    return String(draft.value || "");
  }

  function bind(editor, batchId, sourceSha256, drafts, snapshot, onInput) {
    if (!editor) return;
    editor.value = valueFor(drafts, batchId, sourceSha256);
    if (!ENABLED) return;
    editor.addEventListener("input", () => {
      if (sourceSha256) drafts[batchId] = { sourceSha256, value: editor.value };
      if (onInput) onInput(editor.value);
    });
    if (snapshot?.focused && snapshot.batchId === batchId && snapshot.sourceSha256 === sourceSha256) {
      editor.focus({ preventScroll: true });
      editor.setSelectionRange(
        Math.min(snapshot.selectionStart, editor.value.length),
        Math.min(snapshot.selectionEnd, editor.value.length),
      );
      editor.scrollTop = snapshot.scrollTop;
    }
  }

  function setDisabled(control, disabled) {
    if (!control) return;
    const value = Boolean(disabled);
    if (control.toggleAttribute) control.toggleAttribute("disabled", value);
    control.disabled = value;
  }

  const api = Object.freeze({ VERSION, ENABLED, capture, valueFor, bind, setDisabled });
  root.AmazonConsoleJsonDraft = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : window));
