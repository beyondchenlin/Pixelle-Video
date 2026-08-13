import { verifyRuntime } from "./runtime_contract.mjs";

try {
  const result = await verifyRuntime();
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`HyperFrames runtime verification failed: ${message}\n`);
  process.exitCode = 1;
}
