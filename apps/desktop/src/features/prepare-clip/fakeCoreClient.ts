import type { ErrorCode, PrepareClipRequest } from "../../ipc/types.generated";
import type { CoreClient } from "./coreClient";

export interface FakeCoreOptions {
  /** "success" or the error code the simulated job ends with. */
  outcome?: "success" | ErrorCode;
  /** Pause between simulated events. */
  stepDelayMs?: number;
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason);
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });

/** Simulates the core: progress events, then a result or the configured error. */
export function createFakeCoreClient({
  outcome = "success",
  stepDelayMs = 300,
}: FakeCoreOptions = {}): CoreClient {
  return {
    prepareClip: async (request: PrepareClipRequest, onProgress, signal) => {
      const { id } = request;
      const steps = outcome === "success" ? [0, 50, 100] : [0, 50];
      for (const percent of steps) {
        await wait(stepDelayMs, signal);
        onProgress({ v: 1, id, type: "progress", stage: "downloading", percent });
      }
      if (outcome !== "success") {
        await wait(stepDelayMs, signal);
        return { v: 1, id, type: "error", code: outcome, message: `Simulated ${outcome}` };
      }
      await wait(stepDelayMs, signal);
      onProgress({ v: 1, id, type: "progress", stage: "cutting" });
      await wait(stepDelayMs, signal);
      const { output_dir, title } = request.params;
      const folder = `${output_dir}/${title}`;
      return {
        v: 1,
        id,
        type: "result",
        folder,
        full_track: `${folder}/${title}.mp3`,
        clip: `${folder}/${title} - clip.mp3`,
      };
    },
  };
}
