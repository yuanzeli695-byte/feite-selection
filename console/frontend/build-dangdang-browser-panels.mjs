import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = join(root, "browser-panel-ui-package.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const archivePath = join(root, manifest.sourceArchive);
const archive = readFileSync(archivePath);
const layoutController = readFileSync(join(root, manifest.layoutController), "utf8").replace(/\r\n/g, "\n");
const layoutStyleTemplate = readFileSync(join(root, manifest.layoutStyle), "utf8").replace(/\r\n/g, "\n");

function sha256(value) {
  return createHash("sha256").update(value).digest("hex").toUpperCase();
}

function extract(member) {
  const result = spawnSync("tar", ["-xOf", archivePath, member], {
    encoding: null,
    maxBuffer: 4 * 1024 * 1024,
  });
  if (result.status !== 0 || !result.stdout?.length) {
    const detail = result.stderr?.toString("utf8").trim() || `tar exited with ${result.status}`;
    throw new Error(`Unable to extract ${member}: ${detail}`);
  }
  return result.stdout.toString("utf8").replace(/\r\n/g, "\n");
}

if (manifest.schemaVersion !== "dangdangBrowserPanels/v1") throw new Error("Unsupported browser panel manifest");
if (manifest.package !== "@dangdang/ui" || manifest.packageVersion !== "0.2.5") {
  throw new Error("Unexpected DangDang UI package identity");
}
if (!manifest.layoutFeatureFlag || !manifest.layoutStorageKey || !manifest.bridgeFeatureFlag
  || !manifest.rightOnlyFeatureFlag || !manifest.rightOnlyLayoutFeatureFlag
  || !manifest.rightOnlyLayoutStorageKey) {
  throw new Error("DangDang layout manifest metadata is incomplete");
}
const archiveDigest = sha256(archive);
if (archiveDigest !== manifest.sourceSha256) {
  throw new Error(`DangDang archive hash mismatch: expected ${manifest.sourceSha256}, received ${archiveDigest}`);
}

const packageManifest = JSON.parse(extract("package/package.json"));
if (packageManifest.name !== manifest.package || packageManifest.version !== manifest.packageVersion) {
  throw new Error(`Archive package mismatch: ${packageManifest.name} ${packageManifest.version}`);
}

const targetsByKind = Object.fromEntries(
  manifest.targets.map((target) => [String(target.engine || "").toLowerCase(), target]),
);
for (const [kind, panelId] of [["collector", "ss-collector-panel"], ["runner", "ss-v3-panel"], ["bridge", "asc-v2-panel"]]) {
  const target = targetsByKind[kind];
  if (!target || target.panelId !== panelId || !target.engineVersion) {
    throw new Error(`Manifest target is incomplete for ${kind}`);
  }
  if (kind === "bridge" && (!target.scriptVersion || !target.headingText)) {
    throw new Error("Manifest target is incomplete for bridge version metadata");
  }
}

const sourceModuleCss = manifest.sourceModules.map((member) => extract(member));
const rootMatches = sourceModuleCss[0].match(/:root\s*\{/g) || [];
if (rootMatches.length !== 1) throw new Error(`Expected one :root token block, received ${rootMatches.length}`);
function buildScopedCss({ scope, layoutScope, adapterStyle, requiredSelectors, forbiddenSelectors = [] }) {
  const moduleCss = sourceModuleCss.map((css) => css);
  moduleCss[0] = moduleCss[0].replace(/:root\s*\{/ , `${scope} {`);
  const packageCss = moduleCss.join("\n\n").replace(/\bdd-spin\b/g, "dd-browser-panels-v1-spin");
  const adapterCss = readFileSync(join(root, adapterStyle), "utf8").replace(/\r\n/g, "\n");
  const layoutCss = layoutStyleTemplate.replace(/__DANGDANG_LAYOUT_ROOT__/g, `:is(${layoutScope})`);
  const scopedCss = [
    `/* Generated from ${manifest.package} ${manifest.packageVersion}; archive SHA-256 ${archiveDigest}. */`,
    packageCss,
    adapterCss,
    layoutCss,
  ].join("\n\n");

  const forbiddenCss = [
    [/:root\b/, ":root"],
    [/(^|})\s*\*\s*(,|\{)/m, "global universal selector"],
    [/::-webkit-scrollbar/, "global webkit scrollbar"],
    [/(^|[},])\s*(body|html)(?=[\s.#:[>+~,{])/m, "document-level selector"],
    [/@import\b/, "CSS import"],
    [/url\s*\(/, "CSS URL"],
    [/https?:\/\//, "external CSS URL"],
  ];
  for (const [pattern, label] of forbiddenCss) {
    if (pattern.test(scopedCss)) throw new Error(`Scoped browser panel CSS contains forbidden ${label}`);
  }
  for (const selector of requiredSelectors) {
    if (!scopedCss.includes(selector)) throw new Error(`Scoped browser panel CSS is missing ${selector}`);
  }
  for (const selector of forbiddenSelectors) {
    if (scopedCss.includes(selector)) throw new Error(`Scoped browser panel CSS unexpectedly contains ${selector}`);
  }
  return { css: scopedCss, sha256: sha256(Buffer.from(scopedCss, "utf8")) };
}

function buildUserscript({
  template,
  output,
  featureFlag,
  installUrl,
  css,
  layoutFeatureFlag = manifest.layoutFeatureFlag,
  layoutStorageKey = manifest.layoutStorageKey,
  optionalPlaceholders = [],
}) {
  let source = readFileSync(join(root, template), "utf8").replace(/\r\n/g, "\n");
  const replacements = new Map([
    ["__ADAPTER_VERSION__", manifest.adapterVersion],
    ["__PACKAGE_VERSION__", manifest.packageVersion],
    ["__SCOPED_CSS_SHA256__", css.sha256],
    ["__FEATURE_FLAG__", featureFlag],
    ["__INSTALL_URL__", installUrl],
    ["__COLLECTOR_VERSION__", targetsByKind.collector.engineVersion],
    ["__RUNNER_VERSION__", targetsByKind.runner.engineVersion],
    ["__BRIDGE_VERSION__", targetsByKind.bridge.engineVersion],
    ["__BRIDGE_SCRIPT_VERSION__", targetsByKind.bridge.scriptVersion],
    ["__BRIDGE_HEADING_TEXT__", targetsByKind.bridge.headingText],
    ["__BRIDGE_FEATURE_FLAG__", manifest.bridgeFeatureFlag],
    ["__DANGDANG_SCOPED_CSS__", JSON.stringify(css.css)],
    ["__DANGDANG_PANEL_LAYOUT_CONTROLLER__", layoutController],
    ["__LAYOUT_FEATURE_FLAG__", layoutFeatureFlag],
    ["__LAYOUT_STORAGE_KEY__", layoutStorageKey],
  ]);
  for (const [placeholder, value] of replacements) {
    if (!source.includes(placeholder)) {
      if (optionalPlaceholders.includes(placeholder)) continue;
      throw new Error(`${template} is missing ${placeholder}`);
    }
    source = source.split(placeholder).join(value);
  }
  if (/__[A-Z0-9_]+__/.test(source)) throw new Error(`${template} contains unresolved placeholders`);
  const outputPath = join(root, output);
  writeFileSync(outputPath, source.endsWith("\n") ? source : `${source}\n`, "utf8");
  return { bytes: Buffer.byteLength(source), sha256: css.sha256 };
}

const fullCss = buildScopedCss({
  scope: "#ss-collector-panel.dd-ui,\n#ss-v3-panel.dd-ui,\n#asc-v2-panel.dd-ui",
  layoutScope: "#ss-collector-panel.dd-browser-panel,\n#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel",
  adapterStyle: manifest.adapterStyle,
  requiredSelectors: ["#ss-collector-panel.dd-ui", "#ss-v3-panel.dd-ui", "#asc-v2-panel.dd-ui", ".dd-button", ".dd-textarea", ".dd-badge"],
});
const fullOutput = buildUserscript({
  template: manifest.template,
  output: manifest.output,
  featureFlag: manifest.featureFlag,
  installUrl: manifest.installUrl,
  css: fullCss,
});

const collectorCss = buildScopedCss({
  scope: "#ss-collector-panel.dd-ui",
  layoutScope: "#ss-collector-panel.dd-browser-panel",
  adapterStyle: manifest.collectorOnlyAdapterStyle,
  requiredSelectors: ["#ss-collector-panel.dd-ui", ".dd-button", ".dd-textarea", ".dd-badge"],
  forbiddenSelectors: ["#ss-v3-panel", "#ss-v3-panel.dd-ui", "ss-v3", "#asc-v2-panel", "asc-v2-", "Selection Console Bridge", "2.1.3", "2.1.6"],
});
const collectorOutput = buildUserscript({
  template: manifest.collectorOnlyTemplate,
  output: manifest.collectorOnlyOutput,
  featureFlag: manifest.collectorOnlyFeatureFlag,
  installUrl: manifest.collectorOnlyInstallUrl,
  css: collectorCss,
  optionalPlaceholders: ["__RUNNER_VERSION__", "__BRIDGE_VERSION__", "__BRIDGE_SCRIPT_VERSION__", "__BRIDGE_HEADING_TEXT__", "__BRIDGE_FEATURE_FLAG__"],
});

const rightCss = buildScopedCss({
  scope: "#ss-v3-panel.dd-ui,\n#asc-v2-panel.dd-ui",
  layoutScope: "#ss-v3-panel.dd-browser-panel,\n#asc-v2-panel.dd-browser-panel",
  adapterStyle: manifest.rightOnlyAdapterStyle,
  requiredSelectors: ["#ss-v3-panel.dd-ui", "#asc-v2-panel.dd-ui", ".dd-button", ".dd-textarea", ".dd-badge"],
  forbiddenSelectors: ["#ss-collector-panel", "ss-collector-"],
});
const rightOutput = buildUserscript({
  template: manifest.rightOnlyTemplate,
  output: manifest.rightOnlyOutput,
  featureFlag: manifest.rightOnlyFeatureFlag,
  installUrl: manifest.rightOnlyInstallUrl,
  css: rightCss,
  layoutFeatureFlag: manifest.rightOnlyLayoutFeatureFlag,
  layoutStorageKey: manifest.rightOnlyLayoutStorageKey,
  optionalPlaceholders: ["__COLLECTOR_VERSION__"],
});

console.log(
  `Built DangDang browser panels ${manifest.adapterVersion} (${fullOutput.bytes} bytes, CSS SHA-256 ${fullOutput.sha256})`,
);
console.log(
  `Built Collector-only DangDang panel ${manifest.adapterVersion} (${collectorOutput.bytes} bytes, CSS SHA-256 ${collectorOutput.sha256})`,
);
console.log(
  `Built right-only DangDang panels ${manifest.adapterVersion} (${rightOutput.bytes} bytes, CSS SHA-256 ${rightOutput.sha256})`,
);
