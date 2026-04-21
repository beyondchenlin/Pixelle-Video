import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { createRenderJob, executeRenderJob } from "@hyperframes/producer";

function requireValue(flag, value) {
  if (value === undefined) {
    throw new Error(`Missing value for ${flag}`);
  }
  return value;
}

function parseInteger(flag, value) {
  const parsed = Number.parseInt(requireValue(flag, value), 10);
  if (Number.isNaN(parsed)) {
    throw new Error(`Invalid integer for ${flag}: ${value}`);
  }
  return parsed;
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

function buildJobConfig(options, manifest) {
  const jobConfig = {
    fps: options.fps ?? manifest.fps ?? 30,
    quality: options.quality ?? "standard",
    format: options.format ?? "mp4",
    workers: options.workers,
    useGpu: options.useGpu ?? false,
    hdr: options.hdr ?? false,
  };

  if (options.crf !== undefined) {
    jobConfig.crf = options.crf;
  }
  if (options.videoBitrate !== undefined) {
    jobConfig.videoBitrate = options.videoBitrate;
  }

  return jobConfig;
}

export async function resolveRenderRequest(options) {
  const projectDir = path.resolve(options.projectDir);
  const manifestPath = path.resolve(
    options.manifestPath ?? path.join(projectDir, "data", "render_manifest.json"),
  );
  const manifest = await loadManifest(manifestPath);
  const outputPath = path.resolve(
    options.outputPath ?? path.join(projectDir, "renders", `${manifest.task_id}.mp4`),
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
