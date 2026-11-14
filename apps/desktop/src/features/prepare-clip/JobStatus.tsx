import { Fragment } from "react";
import { errorMessage, SLOW_START_HINT, type JobState } from "./jobState";

const STAGE_LABEL = {
  starting: "Starting",
  downloading: "Downloading",
  cutting: "Cutting",
} as const;

/** Visible wording per stage; differs from the live-region text so the two never collide. */
const STAGE_TITLE = {
  starting: "Starting the audio engine",
  downloading: "Downloading the track",
  cutting: "Cutting the clip",
} as const;

const CARD_CLASS = "rounded-xl border p-4";

const RESULT_ROWS = [
  ["Folder", "folder"],
  ["Full track", "full_track"],
  ["Clip", "clip"],
] as const;

/**
 * Progress, output paths and errors. Stage and completion are announced (visually hidden) by the
 * container's live region.
 */
export function JobStatus({ state }: { state: JobState }) {
  switch (state.status) {
    case "idle":
      return null;
    case "running":
      return (
        <div className={`${CARD_CLASS} border-line bg-surface`}>
          <p className="flex justify-between font-medium">
            <span>{STAGE_TITLE[state.stage]}</span>
            {state.percent !== undefined && <span>{Math.round(state.percent)}%</span>}
          </p>
          <progress
            aria-label={STAGE_LABEL[state.stage]}
            max={100}
            value={state.percent}
            className="mt-2 block h-1.5 w-full appearance-none overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-line [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-accent [&:indeterminate]:animate-pulse [&:indeterminate]:bg-accent/40"
          />
          {state.stage === "starting" && state.slow && (
            <p className="mt-2 text-muted">{SLOW_START_HINT}</p>
          )}
        </div>
      );
    case "success":
      return (
        <div className={`${CARD_CLASS} border-success/40 bg-success/10`}>
          <p className="mb-2 font-semibold text-success">Clip ready</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {RESULT_ROWS.map(([label, key]) => (
              <Fragment key={key}>
                <dt className="text-muted">{label}</dt>
                <dd className="break-all font-mono select-text">{state.result[key]}</dd>
              </Fragment>
            ))}
          </dl>
        </div>
      );
    case "error":
      return (
        <p
          role="alert"
          className={`${CARD_CLASS} border-danger/40 bg-danger/10 font-medium text-danger`}
        >
          {errorMessage(state.code)}
        </p>
      );
  }
}
