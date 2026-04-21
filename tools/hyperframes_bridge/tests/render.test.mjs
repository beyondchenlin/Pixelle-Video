import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { renderProject, resolveRenderRequest } from "../src/render.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..", "..");

async function createProjectDir({ taskId = "task-6", fps = 24 } = {}) {
  const projectDir = await mkdtemp(path.join(tmpdir(), "pixelle-hyperframes-"));
  await mkdir(path.join(projectDir, "data"), { recursive: true });
  await writeFile(
    path.join(projectDir, "data", "render_manifest.json"),
    JSON.stringify({
      task_id: taskId,
      title: "Demo",
      width: 1080,
      height: 1920,
      fps,
      template_id: "image_life_insights_light",
      master_audio_path: null,
      audio_blocks: [],
      sentence_units: [],
      visual_clips: [],
      caption_cues: [],
    }),
    "utf8",
  );
  return projectDir;
}

test("resolveRenderRequest derives render job config from the manifest", async () => {
  const projectDir = await createProjectDir({ taskId: "task-6", fps: 24 });

  const request = await resolveRenderRequest({
    projectDir,
    workers: 2,
    useGpu: true,
  });

  assert.equal(request.projectDir, projectDir);
  assert.equal(request.outputPath, path.join(projectDir, "renders", "task-6.mp4"));
  assert.equal(request.jobConfig.fps, 24);
  assert.equal(request.jobConfig.quality, "standard");
  assert.equal(request.jobConfig.format, "mp4");
  assert.equal(request.jobConfig.workers, 2);
  assert.equal(request.jobConfig.useGpu, true);
  assert.equal(request.jobConfig.hdr, false);
});

test("renderProject calls createRenderJob and executeRenderJob with resolved paths", async () => {
  const projectDir = await createProjectDir({ taskId: "task-9", fps: 30 });
  const progressEvents = [];
  const calls = {};

  const producer = {
    createRenderJob(config) {
      calls.jobConfig = config;
      return { progress: 0, config };
    },
    async executeRenderJob(job, resolvedProjectDir, outputPath, onProgress) {
      calls.job = job;
      calls.projectDir = resolvedProjectDir;
      calls.outputPath = outputPath;
      onProgress?.({ progress: 0.5 }, "halfway");
    },
  };

  const outputPath = await renderProject(
    {
      projectDir,
      quality: "high",
    },
    {
      producer,
      onProgress: (progress, message) => progressEvents.push([progress, message]),
    },
  );

  assert.equal(outputPath, path.join(projectDir, "renders", "task-9.mp4"));
  assert.equal(calls.jobConfig.fps, 30);
  assert.equal(calls.jobConfig.quality, "high");
  assert.equal(calls.projectDir, projectDir);
  assert.equal(calls.outputPath, outputPath);
  assert.deepEqual(progressEvents, [[0.5, "halfway"]]);
});

test("reference templates explicitly pad timelines to the resolved duration", async () => {
  const [indexTemplate, captionsTemplate] = await Promise.all([
    readFile(
      path.join(
        repoRoot,
        "resources/hyperframes/templates/image_life_insights_light/index.html",
      ),
      "utf8",
    ),
    readFile(
      path.join(
        repoRoot,
        "resources/hyperframes/templates/image_life_insights_light/compositions/captions.html",
      ),
      "utf8",
    ),
  ]);

  assert.match(indexTemplate, /function padTimelineToDuration\(timeline, duration\)/);
  assert.match(captionsTemplate, /function padTimelineToDuration\(timeline, duration\)/);
  assert.match(indexTemplate, /padTimelineToDuration\(tl, duration\);/);
  assert.match(captionsTemplate, /padTimelineToDuration\(tl, duration\);/);
});
