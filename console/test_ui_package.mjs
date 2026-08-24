import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => readFileSync(join(root, relativePath), "utf8");
const sha256 = (relativePath) => createHash("sha256").update(readFileSync(join(root, relativePath))).digest("hex").toUpperCase();

test("DangDang UI package assets match the pinned manifest", () => {
  const manifest = JSON.parse(read("ui-package.json"));
  const packageManifest = JSON.parse(read("package.json"));
  assert.equal(manifest.package, "@dangdang/ui");
  assert.equal(manifest.version, "0.2.5");
  assert.ok(existsSync(join(root, manifest.sourceArchive)));
  assert.ok(existsSync(join(root, manifest.styleAsset)));
  assert.equal(sha256(manifest.sourceArchive), manifest.sourceSha256);
  assert.equal(sha256(manifest.styleAsset), manifest.styleSha256);
  assert.equal(packageManifest.scripts["build:ui"], "node frontend/build-dangdang-ui.mjs");
  assert.ok(existsSync(join(root, "frontend/build-dangdang-ui.mjs")));
});

test("DangDang stylesheet and adapter are enabled without replacing the app shell", () => {
  const html = read("static/index.html");
  const adapter = read("static/dangdang-ui-adapter.css");
  const packageCss = read("static/vendor/dangdang-ui-0.2.5.css");

  assert.match(html, /vendor\/dangdang-ui-0\.2\.5\.css/);
  assert.match(html, /dangdang-ui-adapter\.css/);
  assert.match(html, /data-ui-package="dangdang-ui-0\.2\.5"/);
  assert.match(html, /<body class="dd-ui"/);
  assert.match(html, /class="app-shell dd-ui"/);
  assert.doesNotMatch(html, /fluent-components\.js/);
  assert.doesNotMatch(html, /<fluent-/);
  assert.match(packageCss, /\.dd-button/);
  assert.match(packageCss, /--dd-color-accent/);
  assert.match(adapter, /grid-template-columns: minmax\(280px, 320px\)/);
  assert.match(adapter, /height: calc\(100vh - 64px\)/);
  assert.match(adapter, /max-height: min\(45vh, 430px\)/);
  assert.match(adapter, /max-height: min\(34vh, 320px\)/);
  assert.match(adapter, /grid-template-columns: minmax\(0, 1fr\) 68px 72px/);
  assert.match(adapter, /white-space: nowrap/);
  assert.match(adapter, /@media \(max-width: 820px\)[\s\S]*grid-template-columns: 1fr/);
  assert.match(adapter, /@media \(max-width: 820px\)[\s\S]*position: static/);
  assert.match(adapter, /@media \(max-width: 820px\)[\s\S]*min-width: 0/);
});

test("workflow DOM and action contracts remain present", () => {
  const html = read("static/index.html");
  const app = read("static/app.js");
  for (const id of ["categoryPoolInput", "categoryPoolForm", "categoryPoolList", "runsList", "workflow", "candidateStage", "browserStage", "excelStage", "eventLog", "stopButton"]) {
    assert.match(html, new RegExp(`id="${id}"`), `missing #${id}`);
  }
  for (const action of ["prepare-candidates", "load-queue", "approve-queue", "copy-json", "validate-paste", "build-excel"]) {
    assert.match(app, new RegExp(action), `missing data-action contract: ${action}`);
  }
  assert.match(app, /ensureStream\(batch\.id\)/);
  assert.match(app, /postAction\(batch\.id, "excel"/);
  assert.match(app, /dd-button--primary/);
  assert.match(app, /dd-badge--success/);
  assert.match(app, /dd-progress__bar/);
  assert.doesNotMatch(app, /upgradeFluentControls/);
  assert.doesNotMatch(app, /<fluent-/);
});
