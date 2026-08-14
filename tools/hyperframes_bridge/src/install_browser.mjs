import { lstat, mkdir, mkdtemp, readFile, rename, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  Browser,
  BrowserPlatform,
  Cache,
  getDownloadUrl,
  install,
} from "@puppeteer/browsers";
import { PUPPETEER_REVISIONS } from "puppeteer-core/internal/revisions.js";

import {
  defaultBrowserPlatformId,
  verifyBrowserIntegrity,
} from "./browser_integrity.mjs";

const SHA256_RE = /^[a-f0-9]{64}$/;
const BRIDGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MANIFEST_PATH = path.join(BRIDGE_ROOT, "browser_integrity.json");
const DEFAULT_CACHE_DIR = path.join(BRIDGE_ROOT, ".cache", "puppeteer");
const PLATFORM_BY_ID = Object.freeze({
  "linux-x64": BrowserPlatform.LINUX,
  "win32-x64": BrowserPlatform.WIN64,
  "darwin-x64": BrowserPlatform.MAC,
  "darwin-arm64": BrowserPlatform.MAC_ARM,
});

async function isRegularFile(candidate) {
  try {
    const metadata = await lstat(candidate);
    return metadata.isFile() && !metadata.isSymbolicLink();
  } catch {
    return false;
  }
}

export function resolveArchiveContract(manifest, platformId) {
  if (
    manifest?.schema_version !== 2 ||
    manifest?.browser !== "chrome" ||
    typeof manifest?.version !== "string" ||
    !manifest.version.trim()
  ) {
    throw new Error("Unsupported browser integrity manifest format");
  }
  if (manifest.version !== PUPPETEER_REVISIONS.chrome) {
    throw new Error(
      `Browser integrity manifest version does not match Puppeteer: ` +
        `manifest=${manifest.version}, puppeteer=${PUPPETEER_REVISIONS.chrome}`,
    );
  }

  const contract = manifest.archives?.[platformId];
  const puppeteerPlatform = PLATFORM_BY_ID[platformId];
  if (
    !contract ||
    !puppeteerPlatform ||
    contract.puppeteer_platform !== puppeteerPlatform ||
    !SHA256_RE.test(contract.sha256) ||
    !Number.isSafeInteger(contract.bytes) ||
    contract.bytes <= 0
  ) {
    throw new Error(`Browser archive integrity metadata is missing or invalid for ${platformId}`);
  }

  const archiveUrl = new URL(contract.url);
  if (archiveUrl.protocol !== "https:" || archiveUrl.username || archiveUrl.password) {
    throw new Error(`Browser archive URL must use credential-free HTTPS for ${platformId}`);
  }
  const expectedUrl = getDownloadUrl(
    Browser.CHROME,
    puppeteerPlatform,
    manifest.version,
  );
  if (archiveUrl.href !== expectedUrl.href) {
    throw new Error(
      `Browser archive URL mismatch for ${platformId}: expected ${expectedUrl.href}, found ${archiveUrl.href}`,
    );
  }

  return {
    archiveUrl: archiveUrl.href,
    browser: Browser.CHROME,
    buildId: manifest.version,
    bytes: contract.bytes,
    platformId,
    puppeteerPlatform,
    sha256: contract.sha256,
  };
}

async function verifyInstalledTree({ executablePath, manifestPath, platformId }) {
  if (!platformId.startsWith("darwin-")) {
    await verifyBrowserIntegrity({
      browserExecutable: executablePath,
      manifestPath,
      platform: platformId,
    });
  }
}

export async function installPinnedBrowser(
  { cacheDir, manifestPath, platformId = defaultBrowserPlatformId(), fresh = false },
  dependencies = {},
) {
  const installBrowser = dependencies.installBrowser ?? install;
  const resolvedManifestPath = path.resolve(manifestPath);
  const manifest = JSON.parse(await readFile(resolvedManifestPath, "utf8"));
  const contract = resolveArchiveContract(manifest, platformId);
  const resolvedCacheDir = path.resolve(cacheDir);
  const targetCache = new Cache(resolvedCacheDir);
  const targetInstallation = targetCache.installationDir(
    contract.browser,
    contract.puppeteerPlatform,
    contract.buildId,
  );
  const targetExecutable = targetCache.computeExecutablePath({
    browser: contract.browser,
    platform: contract.puppeteerPlatform,
    buildId: contract.buildId,
  });

  if (!fresh && (await isRegularFile(targetExecutable))) {
    await verifyInstalledTree({
      executablePath: targetExecutable,
      manifestPath: resolvedManifestPath,
      platformId,
    });
    return { executablePath: targetExecutable, platformId, reused: true };
  }

  const cacheParent = path.dirname(resolvedCacheDir);
  await mkdir(cacheParent, { recursive: true });
  const stagingCacheDir = await mkdtemp(path.join(cacheParent, ".pixelle-browser-install-"));
  try {
    const installed = await installBrowser({
      browser: contract.browser,
      buildId: contract.buildId,
      cacheDir: stagingCacheDir,
      platform: contract.puppeteerPlatform,
      expectedHash: contract.sha256,
      unpack: true,
    });
    if (!(await isRegularFile(installed.executablePath))) {
      throw new Error(
        `Authenticated browser installation did not create an executable: ${installed.executablePath}`,
      );
    }
    await verifyInstalledTree({
      executablePath: installed.executablePath,
      manifestPath: resolvedManifestPath,
      platformId,
    });

    const relativeExecutable = path.relative(installed.path, installed.executablePath);
    if (relativeExecutable.startsWith("..") || path.isAbsolute(relativeExecutable)) {
      throw new Error("Authenticated browser executable escaped its installation directory");
    }

    await mkdir(path.dirname(targetInstallation), { recursive: true });
    await rm(targetInstallation, { recursive: true, force: true });
    await rename(installed.path, targetInstallation);
    const installedExecutable = path.join(targetInstallation, relativeExecutable);
    if (!(await isRegularFile(installedExecutable))) {
      throw new Error(`Installed browser executable is missing after promotion: ${installedExecutable}`);
    }
    return { executablePath: installedExecutable, platformId, reused: false };
  } finally {
    await rm(stagingCacheDir, { recursive: true, force: true });
  }
}

function parseArguments(argv) {
  const options = {
    fresh: false,
    "cache-dir": process.env.PUPPETEER_CACHE_DIR || DEFAULT_CACHE_DIR,
    manifest: DEFAULT_MANIFEST_PATH,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--fresh") {
      options.fresh = true;
      continue;
    }
    if (!["--cache-dir", "--manifest", "--platform"].includes(token) || argv[index + 1] === undefined) {
      throw new Error(`Invalid pinned browser installer argument: ${token}`);
    }
    options[token.slice(2)] = argv[++index];
  }
  return options;
}

const isDirectRun =
  typeof process.argv[1] === "string" && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  try {
    const options = parseArguments(process.argv.slice(2));
    const result = await installPinnedBrowser({
      cacheDir: options["cache-dir"],
      manifestPath: options.manifest,
      platformId: options.platform,
      fresh: options.fresh,
    });
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
