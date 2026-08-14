import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { Browser, BrowserPlatform, Cache } from "@puppeteer/browsers";

import { computeBrowserTreeDigest } from "../src/browser_integrity.mjs";
import {
  installPinnedBrowser,
  resolveArchiveContract,
} from "../src/install_browser.mjs";

const projectManifestPath = path.resolve("browser_integrity.json");

async function loadProjectManifest() {
  return JSON.parse(await readFile(projectManifestPath, "utf8"));
}

test("archive contracts pin the exact Puppeteer URL and SHA-256 for every supported source platform", async () => {
  const manifest = await loadProjectManifest();

  for (const platformId of ["linux-x64", "win32-x64", "darwin-x64", "darwin-arm64"]) {
    const contract = resolveArchiveContract(manifest, platformId);
    assert.equal(contract.buildId, manifest.version);
    assert.equal(contract.browser, Browser.CHROME);
    assert.equal(contract.archiveUrl, manifest.archives[platformId].url);
    assert.equal(contract.sha256, manifest.archives[platformId].sha256);
  }
});

test("archive contract rejects a changed URL or malformed digest before installation", async () => {
  const manifest = await loadProjectManifest();
  const changedVersion = structuredClone(manifest);
  changedVersion.version = "150.0.0.0";
  assert.throws(
    () => resolveArchiveContract(changedVersion, "win32-x64"),
    /does not match Puppeteer/iu,
  );

  const changedUrl = structuredClone(manifest);
  changedUrl.archives["win32-x64"].url = "https://example.invalid/chrome-win64.zip";
  assert.throws(
    () => resolveArchiveContract(changedUrl, "win32-x64"),
    /archive URL mismatch/iu,
  );

  const changedDigest = structuredClone(manifest);
  changedDigest.archives["win32-x64"].sha256 = "not-a-sha256";
  assert.throws(
    () => resolveArchiveContract(changedDigest, "win32-x64"),
    /metadata is missing or invalid/iu,
  );
});

test("fresh installation passes the pinned digest and promotes only from an isolated staging cache", async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), "pixelle-browser-installer-"));
  t.after(async () => rm(root, { recursive: true, force: true }));
  const cacheDir = path.join(root, "target-cache");
  const manifest = await loadProjectManifest();
  const expected = resolveArchiveContract(manifest, "darwin-x64");
  let observedOptions;

  const result = await installPinnedBrowser(
    {
      cacheDir,
      manifestPath: projectManifestPath,
      platformId: "darwin-x64",
      fresh: true,
    },
    {
      installBrowser: async (options) => {
        observedOptions = options;
        assert.notEqual(path.resolve(options.cacheDir), path.resolve(cacheDir));
        assert.equal(
          path.dirname(path.resolve(options.cacheDir)),
          path.dirname(path.resolve(cacheDir)),
        );

        const stagingCache = new Cache(options.cacheDir);
        const installationPath = stagingCache.installationDir(
          options.browser,
          options.platform,
          options.buildId,
        );
        const executablePath = stagingCache.computeExecutablePath({
          browser: options.browser,
          platform: options.platform,
          buildId: options.buildId,
        });
        await mkdir(path.dirname(executablePath), { recursive: true });
        await writeFile(executablePath, "authenticated-browser", "utf8");
        return { executablePath, path: installationPath };
      },
    },
  );

  assert.equal(observedOptions.expectedHash, expected.sha256);
  assert.equal(observedOptions.unpack, true);
  assert.equal(observedOptions.browser, expected.browser);
  assert.equal(observedOptions.platform, expected.puppeteerPlatform);
  assert.equal(observedOptions.buildId, expected.buildId);
  assert.equal(result.reused, false);
  assert.equal(await readFile(result.executablePath, "utf8"), "authenticated-browser");
  assert.equal(path.resolve(result.executablePath).startsWith(path.resolve(cacheDir)), true);
});

test("existing cache is reused only after complete-tree authentication", async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), "pixelle-browser-reuse-"));
  t.after(async () => rm(root, { recursive: true, force: true }));
  const cacheDir = path.join(root, "cache");
  const manifestPath = path.join(root, "browser_integrity.json");
  const manifest = await loadProjectManifest();
  const cache = new Cache(cacheDir);
  const executablePath = cache.computeExecutablePath({
    browser: Browser.CHROME,
    platform: BrowserPlatform.WIN64,
    buildId: manifest.version,
  });
  await mkdir(path.join(path.dirname(executablePath), "resources"), { recursive: true });
  await writeFile(executablePath, "browser", "utf8");
  const resourcePath = path.join(path.dirname(executablePath), "resources", "data.bin");
  await writeFile(resourcePath, "resource", "utf8");
  const digest = await computeBrowserTreeDigest(executablePath);
  manifest.platforms["win32-x64"] = {
    files: digest.files,
    sha256_tree: digest.sha256Tree,
  };
  await writeFile(manifestPath, JSON.stringify(manifest), "utf8");

  let installerCalled = false;
  const dependencies = {
    installBrowser: async () => {
      installerCalled = true;
      throw new Error("installer must not run for an authenticated cache");
    },
  };
  const reused = await installPinnedBrowser(
    { cacheDir, manifestPath, platformId: "win32-x64" },
    dependencies,
  );
  assert.equal(reused.reused, true);
  assert.equal(installerCalled, false);

  await writeFile(resourcePath, "tampered", "utf8");
  await assert.rejects(
    () =>
      installPinnedBrowser(
        { cacheDir, manifestPath, platformId: "win32-x64" },
        dependencies,
      ),
    /integrity verification failed/iu,
  );
  assert.equal(installerCalled, false);
});
