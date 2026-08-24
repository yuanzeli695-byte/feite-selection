import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(root, "ui-package.json"), "utf8"));
const archivePath = join(root, manifest.sourceArchive);
const stylePath = join(root, manifest.styleAsset);
const result = spawnSync("tar", ["-xOf", archivePath, "package/dist/styles.css"], {
  encoding: null,
  maxBuffer: 4 * 1024 * 1024,
});

if (result.status !== 0 || !result.stdout?.length) {
  const detail = result.stderr?.toString("utf8").trim() || `tar exited with ${result.status}`;
  throw new Error(`Unable to extract ${manifest.package} ${manifest.version}: ${detail}`);
}

const digest = createHash("sha256").update(result.stdout).digest("hex").toUpperCase();
if (digest !== manifest.styleSha256) {
  throw new Error(`DangDang stylesheet hash mismatch: expected ${manifest.styleSha256}, received ${digest}`);
}

writeFileSync(stylePath, result.stdout);
console.log(`Built ${manifest.package} ${manifest.version} stylesheet (${result.stdout.length} bytes, SHA-256 ${digest})`);
