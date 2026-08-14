import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertExecutableWithinCache,
  assertSupportedNodeVersion,
  verifyLockedDependencies,
  verifyRuntime,
} from "../src/runtime_contract.mjs";

const DEPENDENCIES = Object.freeze({
  "@hyperframes/producer": "0.7.107",
  puppeteer: "25.6.0",
  yauzl: "3.4.0",
});

async function writeRuntimeGraph(root, installedOverrides = {}) {
  await writeFile(
    path.join(root, "package.json"),
    JSON.stringify({ dependencies: DEPENDENCIES }),
  );
  await writeFile(
    path.join(root, "package-lock.json"),
    JSON.stringify({ packages: { "": { dependencies: DEPENDENCIES } } }),
  );
  for (const [name, version] of Object.entries(DEPENDENCIES)) {
    const manifestDirectory = path.join(root, "node_modules", ...name.split("/"));
    await mkdir(manifestDirectory, { recursive: true });
    await writeFile(
      path.join(manifestDirectory, "package.json"),
      JSON.stringify({ version: installedOverrides[name] ?? version }),
    );
  }
}

test("runtime contract rejects unsupported Node.js versions", () => {
  assert.throws(() => assertSupportedNodeVersion("22.11.9"), /22\.12\.0 or newer/u);
  assert.doesNotThrow(() => assertSupportedNodeVersion("22.12.0"));
  assert.doesNotThrow(() => assertSupportedNodeVersion("24.12.0"));
});

test("runtime contract rejects an installed dependency that differs from both locks", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pixelle-runtime-lock-"));
  await writeRuntimeGraph(root, { yauzl: "3.3.0" });

  await assert.rejects(
    () => verifyLockedDependencies(root),
    /Installed runtime dependency mismatch for yauzl/u,
  );
});

test("pinned browser verification rejects a system executable outside the cache", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pixelle-runtime-browser-"));
  const cache = path.join(root, "cache");
  const systemDirectory = path.join(root, "system");
  await mkdir(cache);
  await mkdir(systemDirectory);
  const systemBrowser = path.join(systemDirectory, "chrome.exe");
  await writeFile(systemBrowser, "browser");

  await assert.rejects(
    () => assertExecutableWithinCache(systemBrowser, cache),
    /outside the locked Puppeteer cache/u,
  );
});

test("runtime verification accepts the exact lock graph and browser inside the cache", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pixelle-runtime-complete-"));
  await writeRuntimeGraph(root);
  const cache = path.join(root, "cache");
  const browserDirectory = path.join(cache, "chrome", "pinned");
  await mkdir(browserDirectory, { recursive: true });
  const browserPath = path.join(browserDirectory, "chrome.exe");
  await writeFile(browserPath, "browser");
  let verifiedTreeOptions;

  const result = await verifyRuntime({
    bridgeRoot: root,
    environment: {
      PIXELLE_REQUIRE_PINNED_BROWSER: "true",
      PUPPETEER_CACHE_DIR: cache,
    },
    browserPlatform: "win32-x64",
    nodeVersion: "24.12.0",
    resolveBrowser: async () => browserPath,
    verifyBrowserTree: async (options) => {
      verifiedTreeOptions = options;
      return { platform: options.platform, files: 1, sha256Tree: "verified" };
    },
  });

  assert.equal(result.browserPath, await assertExecutableWithinCache(browserPath, cache));
  assert.deepEqual(result.dependencies, DEPENDENCIES);
  assert.equal(verifiedTreeOptions.browserExecutable, result.browserPath);
  assert.equal(verifiedTreeOptions.platform, "win32-x64");
  assert.equal(result.browserIntegrity.sha256Tree, "verified");
});

test("runtime verification rejects an unrecognized pinned-browser policy", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pixelle-runtime-policy-"));
  await writeRuntimeGraph(root);

  await assert.rejects(
    () =>
      verifyRuntime({
        bridgeRoot: root,
        environment: { PIXELLE_REQUIRE_PINNED_BROWSER: "tru" },
        nodeVersion: "24.12.0",
        resolveBrowser: async () => process.execPath,
      }),
    /must be a recognized boolean value/u,
  );
});
