import { errorMessage, SLOW_START_MESSAGE, type JobState } from "./jobState";

const STAGE_LABEL = {
  starting: "Starting",
  downloading: "Downloading",
  cutting: "Cutting",
} as const;

/** Progress, output paths and errors. Stage and completion are announced by the container. */
export function JobStatus({ state }: { state: JobState }) {
  switch (state.status) {
    case "idle":
      return null;
    case "running":
      return (
        <p>
          {state.stage === "starting" && state.slow && <span>{SLOW_START_MESSAGE} </span>}
          <progress aria-label={STAGE_LABEL[state.stage]} max={100} value={state.percent} />
          {state.percent !== undefined && <span> {Math.round(state.percent)}%</span>}
        </p>
      );
    case "success":
      return (
        <dl>
          <dt>Folder</dt>
          <dd>{state.result.folder}</dd>
          <dt>Full track</dt>
          <dd>{state.result.full_track}</dd>
          <dt>Clip</dt>
          <dd>{state.result.clip}</dd>
        </dl>
      );
    case "error":
      return <p role="alert">{errorMessage(state.code)}</p>;
  }
}
