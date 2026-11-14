import type {
  ErrorMessage,
  PrepareClipRequest,
  ProgressEvent,
  ResultMessage,
} from "../../ipc/types.generated";

/**
 * The audio engine (core sidecar) is not available. This is a UI-side outcome that never
 * travels over the IPC contract, so there is no contract error code for it.
 * - `start_failed`: it could not start, or exited before sending any message.
 * - `stopped`: it had already answered (for example sent progress) and then exited.
 */
export interface EngineUnavailable {
  type: "engine_unavailable";
  id: string;
  reason: "start_failed" | "stopped";
  message: string;
}

/** Final outcome of a job: exactly one contract result or error, or the engine being unavailable. */
export type JobOutcome = ResultMessage | ErrorMessage | EngineUnavailable;

/** Port to the core. The real sidecar client implements it in a later phase. */
export interface CoreClient {
  /**
   * Sends the request, reports progress events, then resolves with the result or error.
   * Aborting `signal` cancels the job: the promise rejects and no further events are reported.
   */
  prepareClip: (
    request: PrepareClipRequest,
    onProgress: (event: ProgressEvent) => void,
    signal: AbortSignal,
  ) => Promise<JobOutcome>;
}
