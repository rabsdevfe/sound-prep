import { validateMessage, type IpcIssue } from "../../ipc/messages";
import type { PrepareClipRequest } from "../../ipc/types.generated";

export interface FormValues {
  url: string;
  title: string;
  outputDir: string;
  start: string;
  end: string;
}

export type FieldName = keyof FormValues;
export type FieldErrors = Partial<Record<FieldName, string>>;

export const EMPTY_VALUES: FormValues = {
  url: "",
  title: "",
  outputDir: "",
  start: "",
  end: "",
};

const PARAM_TO_FIELD: Record<string, FieldName> = {
  url: "url",
  title: "title",
  output_dir: "outputDir",
  start: "start",
  end: "end",
};

const TIME_HINT = "Use SS, MM:SS or HH:MM:SS, for example 1:30.";

/** Builds the contract request from raw form values (text fields are trimmed). */
export function buildRequest(values: FormValues, id: string): PrepareClipRequest {
  return {
    v: 1,
    id,
    type: "prepare_clip",
    params: {
      url: values.url.trim(),
      title: values.title.trim(),
      output_dir: values.outputDir,
      start: values.start.trim(),
      end: values.end.trim(),
    },
  };
}

function describeIssue(field: FieldName, value: string, issue: IpcIssue): string {
  switch (field) {
    case "url":
      return value.trim() === "" ? "Enter a YouTube URL." : "Enter a valid http or https URL.";
    case "title":
      return issue.keyword === "maxLength"
        ? "Title must be at most 120 characters."
        : "Enter a title.";
    case "outputDir":
      return "Choose an output directory.";
    case "start":
    case "end":
      return value.trim() === "" ? `Enter the ${field} time. ${TIME_HINT}` : TIME_HINT;
  }
}

/** Converts a validated ClipTime (SS, MM:SS or HH:MM:SS) to seconds. */
export function clipTimeToSeconds(time: string): number {
  return time.split(":").reduce((total, part) => total * 60 + Number(part), 0);
}

/**
 * Validates the form: field rules come from the contract validator; "end after start" is an
 * immediate-feedback rule only (the core stays authoritative).
 */
export function validateForm(values: FormValues): FieldErrors {
  const request = buildRequest(values, "form-validation");
  const errors: FieldErrors = {};
  const result = validateMessage(request);
  if (!result.ok) {
    for (const issue of result.issues) {
      const match = /^\/params\/(\w+)$/.exec(issue.path);
      const field = match ? PARAM_TO_FIELD[match[1]] : undefined;
      if (field && !errors[field]) {
        errors[field] = describeIssue(field, values[field], issue);
      }
    }
  }
  if (
    !errors.start &&
    !errors.end &&
    clipTimeToSeconds(request.params.end) <= clipTimeToSeconds(request.params.start)
  ) {
    errors.end = "End must be after start.";
  }
  return errors;
}
