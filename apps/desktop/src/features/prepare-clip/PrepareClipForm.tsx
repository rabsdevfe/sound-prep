import type { FieldErrors, FieldName, FormValues } from "./formValidation";

export interface PrepareClipFormProps {
  values: FormValues;
  /** Errors to display (already filtered to the fields the user has interacted with). */
  errors: FieldErrors;
  canSubmit: boolean;
  onChange: (field: FieldName, value: string) => void;
  onBlur: (field: FieldName) => void;
  onChooseDirectory: () => void;
  onSubmit: () => void;
}

interface TextFieldProps {
  field: Exclude<FieldName, "outputDir">;
  label: string;
  placeholder?: string;
  props: PrepareClipFormProps;
}

function TextField({ field, label, placeholder, props }: TextFieldProps) {
  const error = props.errors[field];
  const id = `prepare-clip-${field}`;
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={props.values[field]}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => props.onChange(field, event.target.value)}
        onBlur={() => props.onBlur(field)}
      />
      {error && (
        <p id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function PrepareClipForm(props: PrepareClipFormProps) {
  const dirError = props.errors.outputDir;
  return (
    <form
      noValidate
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
        <label htmlFor="prepare-clip-outputDir">Output directory</label>
        <input
          id="prepare-clip-outputDir"
          readOnly
          value={props.values.outputDir}
          placeholder="No directory chosen"
          aria-invalid={dirError ? true : undefined}
          aria-describedby={dirError ? "prepare-clip-outputDir-error" : undefined}
        />
        <button type="button" onClick={props.onChooseDirectory}>
          Choose…
        </button>
        {dirError && (
          <p id="prepare-clip-outputDir-error" role="alert">
            {dirError}
          </p>
        )}
      </div>
      <TextField field="start" label="Start" placeholder="0:00" props={props} />
      <TextField field="end" label="End" placeholder="1:30" props={props} />
      <button type="submit" disabled={!props.canSubmit}>
        Prepare clip
      </button>
    </form>
  );
}
