import assert from "node:assert/strict";
import test from "node:test";

import { resolveGpuEnabled } from "../src/render.mjs";


test("GPU environment disable is a hard kill switch", () => {
  assert.equal(
    resolveGpuEnabled({ useGpu: true }, { PIXELLE_HYPERFRAMES_USE_GPU: "false" }),
    false,
  );
  assert.equal(
    resolveGpuEnabled({ useGpu: true }, { PIXELLE_HYPERFRAMES_USE_GPU: "0" }),
    false,
  );
});


test("explicit GPU request works when environment does not disable it", () => {
  assert.equal(resolveGpuEnabled({ useGpu: true }, {}), true);
  assert.equal(
    resolveGpuEnabled({ useGpu: true }, { PIXELLE_HYPERFRAMES_USE_GPU: "true" }),
    true,
  );
});


test("GPU remains disabled by default without an explicit request", () => {
  assert.equal(resolveGpuEnabled({}, {}), false);
});
