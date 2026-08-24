import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const draftState = require("./static/json-handoff-draft.js");

function fakeEditor(batchId, value = "") {
  const listeners = {};
  return {
    dataset: { batchId, sourceSha256: "sha-a" },
    value,
    selectionStart: value.length,
    selectionEnd: value.length,
    scrollTop: 0,
    focused: false,
    addEventListener(name, callback) { listeners[name] = callback; },
    focus() { this.focused = true; },
    setSelectionRange(start, end) {
      this.selectionStart = start;
      this.selectionEnd = end;
    },
    dispatchInput() { listeners.input(); },
  };
}

test("retains the pasted JSON when polling rebuilds the Excel stage", () => {
  const drafts = {};
  const beforeRefresh = fakeEditor("batch-a", '{"batchName":"vases"}');
  beforeRefresh.selectionStart = 7;
  beforeRefresh.selectionEnd = 12;
  beforeRefresh.scrollTop = 84;

  const snapshot = draftState.capture(beforeRefresh, beforeRefresh, drafts);
  const afterRefresh = fakeEditor("batch-a");
  draftState.bind(afterRefresh, "batch-a", "sha-a", drafts, snapshot);

  assert.equal(draftState.VERSION, "json-handoff-draft-v1.0.0");
  assert.equal(afterRefresh.value, beforeRefresh.value);
  assert.equal(afterRefresh.focused, true);
  assert.deepEqual([afterRefresh.selectionStart, afterRefresh.selectionEnd], [7, 12]);
  assert.equal(afterRefresh.scrollTop, 84);
});

test("keeps drafts isolated by batch and tracks later input", () => {
  const drafts = {
    "batch-a": { sourceSha256: "sha-a", value: "first" },
    "batch-b": { sourceSha256: "sha-b", value: "second" },
  };
  const editor = fakeEditor("batch-b");
  editor.dataset.sourceSha256 = "sha-b";
  draftState.bind(editor, "batch-b", "sha-b", drafts, { batchId: "batch-a", sourceSha256: "sha-a", focused: true });

  assert.equal(editor.value, "second");
  assert.equal(editor.focused, false);
  editor.value = "second-updated";
  editor.dispatchInput();
  assert.deepEqual(drafts, {
    "batch-a": { sourceSha256: "sha-a", value: "first" },
    "batch-b": { sourceSha256: "sha-b", value: "second-updated" },
  });
});

test("drops a draft when the Runner source hash changes", () => {
  const drafts = { "batch-a": { sourceSha256: "old-sha", value: "stale JSON" } };
  const editor = fakeEditor("batch-a");
  draftState.bind(editor, "batch-a", "new-sha", drafts, { batchId: "batch-a", sourceSha256: "old-sha", focused: true });

  assert.equal(editor.value, "");
  assert.equal(editor.focused, false);
  assert.equal(Object.hasOwn(drafts, "batch-a"), false);
});

test("toggles the disabled attribute used by native DangDang buttons", () => {
  const attributes = new Set(["disabled"]);
  const button = {
    disabled: false,
    toggleAttribute(name, enabled) {
      if (enabled) attributes.add(name);
      else attributes.delete(name);
    },
  };

  draftState.setDisabled(button, false);
  assert.equal(button.disabled, false);
  assert.equal(attributes.has("disabled"), false);
  draftState.setDisabled(button, true);
  assert.equal(button.disabled, true);
  assert.equal(attributes.has("disabled"), true);
});
