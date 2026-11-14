import type { ErrorCode, ResultMessage } from "../../ipc/types.generated";

export type JobState =
  | { status: "idle" }
  // "starting" is a UI-only state (request sent, no event yet); it is not part of the IPC contract.
  | { status: "running"; stage: "downloading" | "cutting" | "starting"; percent?: number; slow?: boolean }
  | { status: "success"; result: ResultMessage }
  | { status: "error"; code: ErrorCode | EngineErrorCode };

/** UI-only error kinds for the audio engine; they are not part of the IPC contract. */
export type EngineErrorCode = "engine_start_failed" | "engine_stopped";

/** Human message per core error code. */
export const ERROR_MESSAGES: Record<ErrorCode, string> = {
  invalid_request: "The request was not understood. Check the form and try again.",
  unsupported_version:
    "The app and its audio engine are out of sync. Update the app and try again.",
  invalid_url: "That URL is not a valid YouTube link.",
  invalid_time_range: "The start and end times are not a valid range for this track.",
  invalid_title: "The title cannot be used as a folder name. Try another title.",
  output_dir_unavailable: "The output directory cannot be used. Choose another directory.",
  download_failed: "The track could not be downloaded. Check the URL and your connection.",
  cut_failed: "The clip could not be cut from the track. Check the start and end times.",
  internal_error: "Something went wrong inside the app. Try again.",
};

/** Message per UI-only engine error kind. */
export const ENGINE_MESSAGES: Record<EngineErrorCode, string> = {
  engine_start_failed:
    "The audio engine could not start. Restart the app and try again; if it keeps happening, reinstall the app.",
  engine_stopped:
    "The audio engine stopped unexpectedly. Try again; if it keeps happening, restart the app.",
};

/** Human message for any error state, including the UI-only engine failures. */
export function errorMessage(code: ErrorCode | EngineErrorCode): string {
  return isEngineErrorCode(code) ? ENGINE_MESSAGES[code] : ERROR_MESSAGES[code];
}

function isEngineErrorCode(code: ErrorCode | EngineErrorCode): code is EngineErrorCode {
  return code === "engine_start_failed" || code === "engine_stopped";
}

/** Shown (and announced) when the first start is slow; ADR 0001 measured about 12 s. */
export const SLOW_START_MESSAGE =
  "Starting the audio engine. The first start after an install can take about 12 seconds.";

/** How long "starting" lasts before the slow-start message appears, so warm starts never flash it. */
export const SLOW_START_DELAY_MS = 2000;

const STAGE_ANNOUNCEMENT = {
  starting: "Starting…",
  downloading: "Downloading…",
  cutting: "Cutting…",
};

/** Text for the persistent live region: stage changes and completion, never percent updates. */
export function announcement(state: JobState): string {
  switch (state.status) {
    case "running":
      return state.stage === "starting" && state.slow ? SLOW_START_MESSAGE : STAGE_ANNOUNCEMENT[state.stage];
    case "success":
      return "Done. Your files are ready.";
    default:
      return "";
  }
}
