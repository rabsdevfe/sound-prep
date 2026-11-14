import { useEffect, useRef, useState } from "react";
import type { CoreClient } from "./coreClient";
import { JobStatus } from "./JobStatus";
import { announcement, type JobState } from "./jobState";
import { PrepareClipForm, type PrepareClipFormHandle } from "./PrepareClipForm";
import type { DirectoryPicker, DirectoryStore } from "./ports";
import {
  buildRequest,
  EMPTY_VALUES,
  validateForm,
  type FieldErrors,
  type FieldName,
  type FormValues,
} from "./formValidation";

export interface PrepareClipContainerProps {
  picker: DirectoryPicker;
  store: DirectoryStore;
  client: CoreClient;
}

interface ActiveRun {
  id: string;
  controller: AbortController;
}

const FIELD_ORDER: FieldName[] = ["url", "title", "outputDir", "start", "end"];

export function PrepareClipContainer({ picker, store, client }: PrepareClipContainerProps) {
  const [values, setValues] = useState<FormValues>(() => ({
    ...EMPTY_VALUES,
    outputDir: store.load() ?? "",
  }));
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [dirUnavailable, setDirUnavailable] = useState(false);
  const [touched, setTouched] = useState<Set<FieldName>>(new Set());
  const formRef = useRef<PrepareClipFormHandle>(null);
  // The run whose events are accepted. Cleared when the run settles or the screen unmounts, so
  // late, foreign or stale events can never touch the state; also the synchronous in-flight guard.
  const activeRun = useRef<ActiveRun | null>(null);
  const [job, setJob] = useState<JobState>({ status: "idle" });

  const allErrors = validateForm(values);
  const visibleErrors: FieldErrors = {};
  for (const field of touched) {
    if (allErrors[field]) visibleErrors[field] = allErrors[field];
  }
  if (dirUnavailable) visibleErrors.outputDir = "Choose another directory.";

  useEffect(
    () => () => {
      activeRun.current?.controller.abort();
      activeRun.current = null;
    },
    [],
  );

  const touch = (field: FieldName) => setTouched((prev) => new Set(prev).add(field));

  const handleChoose = async () => {
    let dir: string | null;
    try {
      dir = await picker.pick();
    } catch {
      setPickerError("Could not open the folder picker. Try again.");
      return;
    }
    setPickerError(null);
    if (dir !== null) {
      setValues((prev) => ({ ...prev, outputDir: dir }));
      setDirUnavailable(false);
      store.save(dir);
    }
    touch("outputDir");
  };

  const run = async () => {
    const request = buildRequest(values, crypto.randomUUID());
    const current: ActiveRun = { id: request.id, controller: new AbortController() };
    activeRun.current = current;
    const isCurrent = () => activeRun.current === current;
    setDirUnavailable(false);
    setJob({ status: "running", stage: "starting" });
    try {
      const outcome = await client.prepareClip(
        request,
        (event) => {
          if (isCurrent() && event.id === current.id) {
            setJob({ status: "running", stage: event.stage, percent: event.percent });
          }
        },
        current.controller.signal,
      );
      if (!isCurrent()) return;
      activeRun.current = null;
      if (outcome.id !== null && outcome.id !== current.id) {
        setJob({ status: "error", code: "internal_error" });
      } else if (outcome.type === "result") {
        setJob({ status: "success", result: outcome });
      } else {
        setDirUnavailable(outcome.code === "output_dir_unavailable");
        setJob({ status: "error", code: outcome.code });
      }
    } catch {
      if (!isCurrent()) return;
      activeRun.current = null;
      setJob({ status: "error", code: "internal_error" });
    }
  };

  const handleSubmit = () => {
    if (activeRun.current) return;
    const firstInvalid = FIELD_ORDER.find((field) => allErrors[field]);
    if (firstInvalid) {
      setTouched(new Set(FIELD_ORDER));
      formRef.current?.focusField(firstInvalid);
      return;
    }
    void run();
  };

  return (
    <>
      <PrepareClipForm
        handleRef={formRef}
        values={values}
        errors={visibleErrors}
        submitDisabled={job.status === "running"}
        onChange={(field, value) => setValues((prev) => ({ ...prev, [field]: value }))}
        onBlur={touch}
        onChooseDirectory={() => void handleChoose()}
        onSubmit={handleSubmit}
      />
      {pickerError && <p role="alert">{pickerError}</p>}
      <div role="status">{announcement(job)}</div>
      <JobStatus state={job} />
    </>
  );
}
