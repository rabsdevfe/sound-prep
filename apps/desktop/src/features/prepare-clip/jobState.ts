import type { ErrorCode, ResultMessage } from "../../ipc/types.generated";

export type JobState =
  | { status: "idle" }
  // "starting" is a UI-only state (request sent, no event yet); it is not part of the IPC contract.
  | { status: "running"; stage: "downloading" | "cutting" | "starting"; percent?: number }
  | { status: "success"; result: ResultMessage }
  | { status: "error"; code: ErrorCode };

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

const STAGE_ANNOUNCEMENT = {
  starting: "Starting…",
  downloading: "Downloading…",
  cutting: "Cutting…",
};

/** Text for the persistent live region: stage changes and completion, never percent updates. */
export function announcement(state: JobState): string {
  switch (state.status) {
    case "running":
      return STAGE_ANNOUNCEMENT[state.stage];
    case "success":
      return "Done. Your files are ready.";
    default:
      return "";
  }
}
