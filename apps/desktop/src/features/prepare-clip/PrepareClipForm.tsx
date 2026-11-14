import { useImperativeHandle, useRef, type Ref } from "react";
import type { FieldErrors, FieldName, FormValues } from "./formValidation";

export interface PrepareClipFormHandle {
  focusField: (field: FieldName) => void;
}

export interface PrepareClipFormProps {
  handleRef?: Ref<PrepareClipFormHandle>;
  values: FormValues;
  /** Errors to display (already filtered to the fields the user has interacted with). */
  errors: FieldErrors;
  submitDisabled: boolean;
  onChange: (field: FieldName, value: string) => void;
  onBlur: (field: FieldName) => void;
  onChooseDirectory: () => void;
  onSubmit: () => void;
}

const INPUT_CLASS =
  "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-[13px] text-ink " +
  "placeholder:text-muted aria-invalid:border-danger";
const LABEL_CLASS = "mb-1 block text-[13px] font-medium";
const TIME_HINT_ID = "prepare-clip-time-hint";
const ERROR_CLASS = "mt-1 text-[13px] text-danger";

interface TextFieldProps {
  field: Exclude<FieldName, "outputDir">;
  label: string;
  placeholder?: string;
  /** Id of an always-visible hint element that also describes the input. */
  hintId?: string;
  props: PrepareClipFormProps;
}

function TextField({ field, label, placeholder, hintId, props }: TextFieldProps) {
  const error = props.errors[field];
  const id = `prepare-clip-${field}`;
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLASS}>
        {label}
      </label>
      <input
        id={id}
        className={INPUT_CLASS}
        value={props.values[field]}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={[error ? `${id}-error` : null, hintId].filter(Boolean).join(" ") || undefined}
        onChange={(event) => props.onChange(field, event.target.value)}
        onBlur={() => props.onBlur(field)}
      />
      {error && (
        <p id={`${id}-error`} className={ERROR_CLASS}>
          {error}
        </p>
      )}
    </div>
  );
}

export function PrepareClipForm(props: PrepareClipFormProps) {
  const formElement = useRef<HTMLFormElement>(null);
  useImperativeHandle(props.handleRef, () => ({
    focusField: (field) => {
      const input = formElement.current?.elements.namedItem(`prepare-clip-${field}`);
      if (input instanceof HTMLInputElement) input.focus();
    },
  }));

  const dirError = props.errors.outputDir;
  return (
    <form
      ref={formElement}
      noValidate
      className="flex flex-col gap-3.5 rounded-xl border border-line bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        props.onSubmit();
      }}
    >
      <TextField
        field="url"
        label="YouTube URL"
        placeholder="https://www.youtube.com/watch?v=…"
        props={props}
      />
      <TextField field="title" label="Title" props={props} />
      <div>
        <label htmlFor="prepare-clip-outputDir" className={LABEL_CLASS}>
          Output directory
        </label>
        <div className="flex gap-2">
          <input
            id="prepare-clip-outputDir"
            className={`${INPUT_CLASS} min-w-0 flex-1 truncate`}
            readOnly
            value={props.values.outputDir}
            placeholder="No directory chosen"
            aria-invalid={dirError ? true : undefined}
            aria-describedby={dirError ? "prepare-clip-outputDir-error" : undefined}
          />
          <button
            type="button"
            className="shrink-0 rounded-md border border-line bg-surface px-3 py-1.5 text-[13px] hover:bg-canvas active:bg-line"
            onClick={props.onChooseDirectory}
          >
            Choose…
          </button>
        </div>
        {dirError && (
          <p id="prepare-clip-outputDir-error" className={ERROR_CLASS}>
            {dirError}
          </p>
        )}
      </div>
      <div>
        <div className="grid grid-cols-2 gap-3">
          <TextField field="start" label="Start" placeholder="0:00" hintId={TIME_HINT_ID} props={props} />
          <TextField field="end" label="End" placeholder="1:30" hintId={TIME_HINT_ID} props={props} />
        </div>
        <p id={TIME_HINT_ID} className="mt-1.5 text-[13px] text-muted">Times as 1:30 or 1:02:30.</p>
      </div>
      <button
        type="submit"
        className="rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-accent-ink hover:brightness-110 active:brightness-95 aria-disabled:cursor-default aria-disabled:bg-line aria-disabled:text-ink aria-disabled:hover:brightness-100"
        aria-disabled={props.submitDisabled || undefined}
      >
        Prepare clip
      </button>
    </form>
  );
}
