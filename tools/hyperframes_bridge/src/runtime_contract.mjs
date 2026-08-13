import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolveBrowserExecutable } from "./render.mjs";

export const REQUIRED_RUNTIME_DEPENDENCIES = Object.freeze([
  "@hyperframes/producer",
  "puppeteer",
  "yauzl",
]);

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off"]);
const MINIMUM_NODE_VERSION = Object.freeze({ major: 22, minor: 12, patch: 0 });
const DEFAULT_BRIDGE_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

function environmentValue(environment, name) {
  const matchingKey = Object.keys(environment).find(
    (candidate) => candidate.toLowerCase() === name.toLowerCase(),
  );
  return matchingKey ? environment[matchingKey] : undefined;
}

function parseNodeVersion(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)/u.exec(String(version));
  if (!match) {
    throw new Error(`Unable to parse Node.js version: ${version}`);
  }
  return match.slice(1).map(Number);
}

export function assertSupportedNodeVersion(version = process.versions.node) {
  const [major, minor, patchVersion] = parseNodeVersion(version);
  const supported =
    major > MINIMUM_NODE_VERSION.major ||
    (major === MINIMUM_NODE_VERSION.major &&
      (minor > MINIMUM_NODE_VERSION.minor ||
        (minor === MINIMUM_NODE_VERSION.minor &&
          patchVersion >= MINIMUM_NODE_VERSION.patch)));
  if (!supported) {
    throw new Error(
      `Node.js 22.12.0 or newer is required; found ${version}`,
    );
  }
}

async function readJson(filePath) {
  let payload;
  try {
    payload = JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    throw new Error(`Unable to read locked runtime manifest: ${filePath}`, {
      cause: error,
    });
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Locked runtime manifest must contain an object: ${filePath}`);
  }
  return payload;
}

export async function verifyLockedDependencies(bridgeRoot = DEFAULT_BRIDGE_ROOT) {
  const resolvedRoot = path.resolve(bridgeRoot);
  const packageManifest = await readJson(path.join(resolvedRoot, "package.json"));
  const lockManifest = await readJson(path.join(resolvedRoot, "package-lock.json"));
  const declaredDependencies = packageManifest.dependencies ?? {};
  const lockedDependencies = lockManifest.packages?.[""]?.dependencies ?? {};
  const versions = {};

  for (const dependencyName of REQUIRED_RUNTIME_DEPENDENCIES) {
    const declaredVersion = declaredDependencies[dependencyName];
    if (typeof declaredVersion !== "string" || declaredVersion.trim().length === 0) {
      throw new Error(`Missing exact runtime dependency declaration: ${dependencyName}`);
    }
    if (lockedDependencies[dependencyName] !== declaredVersion) {
      throw new Error(
        `Runtime lock mismatch for ${dependencyName}: ` +
          `package.json=${declaredVersion}, package-lock.json=${lockedDependencies[dependencyName] ?? "missing"}`,
      );
    }

    const installedManifestPath = path.join(
      resolvedRoot,
      "node_modules",
      ...dependencyName.split("/"),
      "package.json",
    );
    const installedManifest = await readJson(installedManifestPath);
    if (installedManifest.version !== declaredVersion) {
      throw new Error(
        `Installed runtime dependency mismatch for ${dependencyName}: ` +
          `expected=${declaredVersion}, installed=${installedManifest.version ?? "missing"}`,
      );
    }
    versions[dependencyName] = declaredVersion;
  }

  return versions;
}

export async function assertExecutableWithinCache(executablePath, cacheDirectory) {
  if (!cacheDirectory || String(cacheDirectory).trim().length === 0) {
    throw new Error(
      "PUPPETEER_CACHE_DIR is required when pinned-browser verification is enabled",
    );
  }
  const [resolvedExecutable, resolvedCache] = await Promise.all([
    realpath(path.resolve(executablePath)),
    realpath(path.resolve(cacheDirectory)),
  ]);
  const relativePath = path.relative(resolvedCache, resolvedExecutable);
  if (
    relativePath === "" ||
    relativePath === ".." ||
    relativePath.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativePath)
  ) {
    throw new Error(
      `Resolved browser is outside the locked Puppeteer cache: ${resolvedExecutable}`,
    );
  }
  return resolvedExecutable;
}

export async function verifyRuntime(options = {}) {
  const bridgeRoot = path.resolve(options.bridgeRoot ?? DEFAULT_BRIDGE_ROOT);
  const environment = options.environment ?? process.env;
  const resolveBrowser = options.resolveBrowser ?? resolveBrowserExecutable;

  assertSupportedNodeVersion(options.nodeVersion ?? process.versions.node);
  const dependencies = await verifyLockedDependencies(bridgeRoot);
  const browserPath = await resolveBrowser({}, { environment });
  const rawPinnedBrowserPolicy = String(
    environmentValue(environment, "PIXELLE_REQUIRE_PINNED_BROWSER") ?? "",
  )
    .trim()
    .toLowerCase();
  if (
    rawPinnedBrowserPolicy &&
    !TRUE_VALUES.has(rawPinnedBrowserPolicy) &&
    !FALSE_VALUES.has(rawPinnedBrowserPolicy)
  ) {
    throw new Error(
      "PIXELLE_REQUIRE_PINNED_BROWSER must be a recognized boolean value",
    );
  }
  const requirePinnedBrowser = TRUE_VALUES.has(rawPinnedBrowserPolicy);
  const verifiedBrowserPath = requirePinnedBrowser
    ? await assertExecutableWithinCache(
        browserPath,
        environmentValue(environment, "PUPPETEER_CACHE_DIR"),
      )
    : path.resolve(browserPath);

  return {
    nodeVersion: options.nodeVersion ?? process.versions.node,
    dependencies,
    browserPath: verifiedBrowserPath,
    pinnedBrowserRequired: requirePinnedBrowser,
  };
}
