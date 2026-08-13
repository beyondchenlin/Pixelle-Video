import { constants as fsConstants } from "node:fs";
import { access, mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { createRenderJob, executeRenderJob, resolveConfig } from "@hyperframes/producer";
import puppeteer from "puppeteer";

const SAFE_MANIFEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const FALSE_ENV_VALUES = new Set(["0", "false", "no", "off"]);

function requireValue(flag, value) {
  if (value === undefined) {
    throw new Error(`Missing value for ${flag}`);
  }
  return value;
}

function parseInteger(flag, value) {
  const rawValue = requireValue(flag, value);
  if (!/^[+-]?\d+$/.test(rawValue)) {
    throw new Error(`Invalid integer for ${flag}: ${value}`);
  }
  const parsed = Number(rawValue);
  if (!Number.isSafeInteger(parsed)) {
    throw new Error(`Integer out of safe range for ${flag}: ${value}`);
  }
  return parsed;
}

function requireIntegerInRange(fieldName, value, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${fieldName} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

function requireChoice(fieldName, value, choices) {
  if (!choices.includes(value)) {
    throw new Error(`${fieldName} must be one of: ${choices.join(", ")}`);
  }
  return value;
}

export function parseArgs(argv) {
  const options = {};

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];

    switch (token) {
      case "--project-dir":
        options.projectDir = requireValue(token, argv[++index]);
        break;
      case "--manifest-path":
        options.manifestPath = requireValue(token, argv[++index]);
        break;
      case "--output-path":
        options.outputPath = requireValue(token, argv[++index]);
        break;
      case "--chrome-path":
        options.chromePath = requireValue(token, argv[++index]);
        break;
      case "--fps":
        options.fps = parseInteger(token, argv[++index]);
        break;
      case "--workers":
        options.workers = parseInteger(token, argv[++index]);
        break;
      case "--quality":
        options.quality = requireValue(token, argv[++index]);
        break;
      case "--format":
        options.format = requireValue(token, argv[++index]);
        break;
      case "--crf":
        options.crf = parseInteger(token, argv[++index]);
        break;
      case "--video-bitrate":
        options.videoBitrate = requireValue(token, argv[++index]);
        break;
      case "--use-gpu":
        options.useGpu = true;
        break;
      case "--hdr":
        options.hdr = true;
        break;
      default:
        throw new Error(`Unknown argument: ${token}`);
    }
  }

  if (!options.projectDir) {
    throw new Error("--project-dir is required");
  }

  return options;
}

async function loadManifest(manifestPath) {
  const manifestRaw = await readFile(manifestPath, "utf8");
  return JSON.parse(manifestRaw);
}

function validateManifestIdentifier(fieldName, value) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`Invalid ${fieldName}: expected non-empty string`);
  }

  const candidate = value.trim();
  if (!SAFE_MANIFEST_ID_RE.test(candidate)) {
    throw new Error(
      `Invalid ${fieldName}: ${JSON.stringify(value)}. Expected letters, numbers, hyphens, or underscores only.`,
    );
  }

  return candidate;
}

function environmentValue(environment, name) {
  const matchingKey = Object.keys(environment).find(
    (candidate) => candidate.toLowerCase() === name.toLowerCase(),
  );
  return matchingKey ? environment[matchingKey] : undefined;
}

export function resolveGpuEnabled(options = {}, environment = process.env) {
  const configured = environmentValue(environment, "PIXELLE_HYPERFRAMES_USE_GPU");
  const normalized = typeof configured === "string" ? configured.trim().toLowerCase() : "";
  if (FALSE_ENV_VALUES.has(normalized)) {
    return false;
  }
  return options.useGpu ?? false;
}

function buildJobConfig(options, manifest) {
  const fps = requireIntegerInRange("fps", options.fps ?? manifest.fps ?? 30, 1, 120);
  const workers =
    options.workers === undefined
      ? undefined
      : requireIntegerInRange("workers", options.workers, 1, 64);
  const jobConfig = {
    fps,
    quality: requireChoice("quality", options.quality ?? "standard", ["draft", "standard", "high"]),
    format: requireChoice("format", options.format ?? "mp4", ["mp4", "webm", "mov"]),
    workers,
    useGpu: resolveGpuEnabled(options),
    hdr: options.hdr ?? false,
  };

  if (options.chromePath) {
    jobConfig.producerConfig = {
      ...resolveConfig(),
      chromePath: options.chromePath,
    };
  }

  if (options.crf !== undefined) {
    jobConfig.crf = requireIntegerInRange("crf", options.crf, 0, 51);
  }
  if (options.videoBitrate !== undefined) {
    jobConfig.videoBitrate = options.videoBitrate;
  }

  return jobConfig;
}

async function isUsableBrowserExecutable(candidate, platform) {
  if (!candidate || candidate.trim().length === 0) return false;
  try {
    await access(
      path.resolve(candidate),
      platform === "win32" ? fsConstants.F_OK : fsConstants.X_OK,
    );
    return (await stat(path.resolve(candidate))).isFile();
  } catch {
    return false;
  }
}

export async function resolveBrowserExecutable(options = {}, dependencies = {}) {
  const environment = dependencies.environment ?? process.env;
  const platform = dependencies.platform ?? process.platform;
  const explicitlyConfigured =
    options.chromePath ??
    environmentValue(environment, "PRODUCER_HEADLESS_SHELL_PATH") ??
    environmentValue(environment, "PUPPETEER_EXECUTABLE_PATH");
  if (explicitlyConfigured?.trim()) {
    const explicitPath = path.resolve(explicitlyConfigured.trim());
    if (!(await isUsableBrowserExecutable(explicitPath, platform))) {
      throw new Error(`Configured browser executable does not exist or is not executable: ${explicitPath}`);
    }
    return explicitPath;
  }

  const puppeteerExecutablePath =
    dependencies.puppeteerExecutablePath ?? (() => puppeteer.executablePath());
  try {
    const pinnedPath = path.resolve(await puppeteerExecutablePath());
    if (await isUsableBrowserExecutable(pinnedPath, platform)) {
      return pinnedPath;
    }
  } catch {
    // Continue to system browsers and report one consolidated diagnostic below.
  }

  throw new Error(
    "The browser pinned by Puppeteer is not installed. " +
      "Run `npm run browser:install` in tools/hyperframes_bridge " +
      "or explicitly set PRODUCER_HEADLESS_SHELL_PATH or PUPPETEER_EXECUTABLE_PATH " +
      "to an existing executable.",
  );
}

export async function resolveRenderRequest(options) {
  const projectDir = path.resolve(options.projectDir);
  const manifestPath = path.resolve(
    options.manifestPath ?? path.join(projectDir, "data", "render_manifest.json"),
  );
  const manifest = await loadManifest(manifestPath);
  const taskId = validateManifestIdentifier("task_id", manifest.task_id);
  const outputPath = path.resolve(
    options.outputPath ?? path.join(projectDir, "renders", `${taskId}.mp4`),
  );

  await mkdir(path.dirname(outputPath), { recursive: true });

  return {
    projectDir,
    manifestPath,
    manifest,
    outputPath,
    jobConfig: buildJobConfig(options, manifest),
  };
}

export async function renderProject(options, dependencies = {}) {
  const producer = dependencies.producer ?? { createRenderJob, executeRenderJob };
  const request = await resolveRenderRequest(options);
  const chromePath = await resolveBrowserExecutable(options, dependencies.browser);
  request.jobConfig.producerConfig = {
    ...resolveConfig(),
    chromePath,
  };
  const job = producer.createRenderJob(request.jobConfig);
  const onProgress =
    typeof dependencies.onProgress === "function"
      ? (progressJob, message) => {
          dependencies.onProgress(progressJob?.progress ?? 0, message ?? "");
        }
      : undefined;

  await producer.executeRenderJob(job, request.projectDir, request.outputPath, onProgress);
  return request.outputPath;
}

export async function main(argv = process.argv.slice(2), dependencies = {}) {
  const outputStream = dependencies.stdout ?? process.stdout;
  const progressStream = dependencies.stderr ?? process.stderr;
  const options = parseArgs(argv);

  const outputPath = await renderProject(options, {
    producer: dependencies.producer,
    onProgress: (progress, message) => {
      progressStream.write(`${JSON.stringify({ type: "progress", progress, message })}\n`);
    },
  });

  outputStream.write(`${JSON.stringify({ output_path: outputPath })}\n`);
  return outputPath;
}

const isDirectRun =
  typeof process.argv[1] === "string" && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  main().catch((error) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}
