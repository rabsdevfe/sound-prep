import type {
  ErrorMessage,
  PrepareClipRequest,
  ProgressEvent,
  ResultMessage,
} from "../../ipc/types.generated";

/** Final outcome of a job: exactly one result or error, as in the IPC contract. */
export type JobOutcome = ResultMessage | ErrorMessage;

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
