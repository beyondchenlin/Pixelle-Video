import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  computeBrowserTreeDigest,
  defaultBrowserPlatformId,
  verifyBrowserIntegrity,
} from "../src/browser_integrity.mjs";

async function createBrowserFixture() {
  const root = await mkdtemp(path.join(tmpdir(), "pixelle-browser-integrity-"));
  const browserRoot = path.join(root, "browser");
  const resources = path.join(browserRoot, "resources");
  await mkdir(resources, { recursive: true });
  const executable = path.join(browserRoot, process.platform === "win32" ? "chrome.exe" : "chrome");
  await writeFile(executable, "browser-binary", "utf8");
  await writeFile(path.join(resources, "data.bin"), "browser-resource", "utf8");
  return { root, executable };
}

test("browser platform mapping rejects unsupported host combinations", () => {
  assert.equal(defaultBrowserPlatformId("linux", "x64"), "linux-x64");
  assert.equal(defaultBrowserPlatformId("win32", "arm64"), "win32-x64");
  assert.equal(defaultBrowserPlatformId("darwin", "arm64"), "darwin-arm64");
  assert.throws(
    () => defaultBrowserPlatformId("linux", "arm64"),
    /Unsupported pinned browser platform/u,
  );
});

test("browser integrity manifest authenticates the complete runtime tree", async () => {
  const fixture = await createBrowserFixture();
  const actual = await computeBrowserTreeDigest(fixture.executable);
  const manifestPath = path.join(fixture.root, "browser_integrity.json");
  await writeFile(
    manifestPath,
    JSON.stringify({
      schema_version: 2,
      browser: "chrome",
      version: "test",
      algorithm: "sha256-tree-v1",
      platforms: {
        test: { files: actual.files, sha256_tree: actual.sha256Tree },
      },
    }),
    "utf8",
  );

  const verified = await verifyBrowserIntegrity({
    browserExecutable: fixture.executable,
    manifestPath,
    platform: "test",
  });

  assert.equal(verified.files, 2);
  assert.equal(verified.sha256Tree, actual.sha256Tree);
});

test("browser integrity verification rejects a changed browser resource", async () => {
  const fixture = await createBrowserFixture();
  const actual = await computeBrowserTreeDigest(fixture.executable);
  const manifestPath = path.join(fixture.root, "browser_integrity.json");
  await writeFile(
    manifestPath,
    JSON.stringify({
      schema_version: 2,
      browser: "chrome",
      version: "test",
      algorithm: "sha256-tree-v1",
      platforms: {
        test: { files: actual.files, sha256_tree: actual.sha256Tree },
      },
    }),
    "utf8",
  );
  await writeFile(
    path.join(path.dirname(fixture.executable), "resources", "data.bin"),
    "tampered",
    "utf8",
  );

  await assert.rejects(
    () =>
      verifyBrowserIntegrity({
        browserExecutable: fixture.executable,
        manifestPath,
        platform: "test",
      }),
    /integrity verification failed/iu,
  );
});
