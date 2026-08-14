import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const SHA256_RE = /^[a-f0-9]{64}$/;

function compareText(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

export function defaultBrowserPlatformId(platform = process.platform, arch = process.arch) {
  if (platform === "linux" && arch === "x64") return "linux-x64";
  if (platform === "win32" && (arch === "x64" || arch === "arm64")) return "win32-x64";
  if (platform === "darwin" && arch === "x64") return "darwin-x64";
  if (platform === "darwin" && arch === "arm64") return "darwin-arm64";
  throw new Error(`Unsupported pinned browser platform: ${platform}-${arch}`);
}

async function collectFiles(root, directory = root, files = []) {
  const entries = await readdir(directory, { withFileTypes: true });
  entries.sort((left, right) => compareText(left.name, right.name));
  for (const entry of entries) {
    const candidate = path.join(directory, entry.name);
    const metadata = await lstat(candidate);
    if (metadata.isSymbolicLink()) {
      throw new Error(`Browser runtime contains a symbolic link or reparse point: ${candidate}`);
    }
    if (metadata.isDirectory()) {
      await collectFiles(root, candidate, files);
      continue;
    }
    if (!metadata.isFile()) {
      throw new Error(`Browser runtime contains an unsupported filesystem entry: ${candidate}`);
    }
    files.push({
      absolutePath: candidate,
      relativePath: path.relative(root, candidate).split(path.sep).join("/"),
      size: metadata.size,
    });
  }
  return files;
}

export async function computeBrowserTreeDigest(browserExecutable) {
  const executable = path.resolve(browserExecutable);
  const executableMetadata = await lstat(executable);
  if (!executableMetadata.isFile() || executableMetadata.isSymbolicLink()) {
    throw new Error(`Browser executable is not a regular file: ${executable}`);
  }

  const root = path.dirname(executable);
  const files = await collectFiles(root);
  files.sort((left, right) => compareText(left.relativePath, right.relativePath));

  const digest = createHash("sha256");
  for (const file of files) {
    digest.update(file.relativePath, "utf8");
    digest.update("\0");
    digest.update(String(file.size), "ascii");
    digest.update("\0");
    for await (const chunk of createReadStream(file.absolutePath)) {
      digest.update(chunk);
    }
    digest.update("\0");
  }

  return {
    root,
    files: files.length,
    sha256Tree: digest.digest("hex"),
  };
}

export async function verifyBrowserIntegrity({ browserExecutable, manifestPath, platform }) {
  const manifest = JSON.parse(await readFile(path.resolve(manifestPath), "utf8"));
  if (manifest.schema_version !== 2 || manifest.algorithm !== "sha256-tree-v1") {
    throw new Error("Unsupported browser integrity manifest format");
  }
  const expected = manifest.platforms?.[platform];
  if (!expected || !SHA256_RE.test(expected.sha256_tree) || !Number.isSafeInteger(expected.files)) {
    throw new Error(`Browser integrity metadata is missing or invalid for ${platform}`);
  }

  const actual = await computeBrowserTreeDigest(browserExecutable);
  if (actual.files !== expected.files || actual.sha256Tree !== expected.sha256_tree) {
    throw new Error(
      `Browser integrity verification failed for ${platform}: ` +
        `expected ${expected.files} files/${expected.sha256_tree}, ` +
        `found ${actual.files} files/${actual.sha256Tree}`,
    );
  }

  return {
    browser: manifest.browser,
    version: manifest.version,
    platform,
    ...actual,
  };
}

function parseArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!["--browser", "--manifest", "--platform"].includes(token) || argv[index + 1] === undefined) {
      throw new Error(`Invalid browser integrity argument: ${token}`);
    }
    options[token.slice(2)] = argv[++index];
  }
  for (const required of ["browser", "manifest", "platform"]) {
    if (!options[required]) throw new Error(`--${required} is required`);
  }
  return options;
}

const isDirectRun =
  typeof process.argv[1] === "string" && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  try {
    const options = parseArguments(process.argv.slice(2));
    const result = await verifyBrowserIntegrity({
      browserExecutable: options.browser,
      manifestPath: options.manifest,
      platform: options.platform,
    });
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
