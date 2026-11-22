import { Fragment } from "react";
import type { ResultMessage } from "../../ipc/types.generated";
import { errorMessage, SLOW_START_HINT, type JobState } from "./jobState";

const STAGE_LABEL = {
  starting: "Starting",
  downloading: "Downloading",
  cutting: "Cutting",
  separating: "Separating",
} as const;

/** Visible wording per stage; differs from the live-region text so the two never collide. */
const STAGE_TITLE = {
  starting: "Starting the audio engine",
  downloading: "Downloading the track",
  cutting: "Cutting the clip",
  separating: "Separating the stems",
} as const;

const CARD_CLASS = "rounded-xl border p-4";

const STEM_NAMES = ["drums", "bass", "vocals", "guitar", "other"] as const;

/** Label and path per output; a result carries either a clip or stems, never neither. */
function resultRows(result: ResultMessage): [string, string][] {
  const rows: [string, string][] = [
    ["Folder", result.folder],
    ["Full track", result.full_track],
  ];
  if (result.clip !== undefined) rows.push(["Clip", result.clip]);
  if (result.stems !== undefined) {
    for (const name of STEM_NAMES) rows.push([`Stem: ${name}`, result.stems[name]]);
  }
  return rows;
}

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
          <p className="mb-2 font-semibold text-success">{state.result.stems !== undefined ? "Stems ready" : "Clip ready"}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {resultRows(state.result).map(([label, path]) => (
              <Fragment key={label}>
                <dt className="text-muted">{label}</dt>
                <dd className="break-all font-mono select-text">{path}</dd>
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
