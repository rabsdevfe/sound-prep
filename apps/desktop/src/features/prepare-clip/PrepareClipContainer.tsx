import { useState } from "react";
import type { PrepareClipRequest } from "../../ipc/types.generated";
import { PrepareClipForm } from "./PrepareClipForm";
import {
  buildRequest,
  EMPTY_VALUES,
  validateForm,
  type FieldErrors,
  type FieldName,
  type FormValues,
} from "./formValidation";

export interface PrepareClipContainerProps {
  /** Resolves to the chosen absolute directory, or null when the user cancels. */
  chooseDirectory: () => Promise<string | null>;
  onSubmit: (request: PrepareClipRequest) => void;
}

export function PrepareClipContainer({ chooseDirectory, onSubmit }: PrepareClipContainerProps) {
  const [values, setValues] = useState<FormValues>(EMPTY_VALUES);
  const [touched, setTouched] = useState<Set<FieldName>>(new Set());

  const allErrors = validateForm(values);
  const visibleErrors: FieldErrors = {};
  for (const field of touched) {
    if (allErrors[field]) visibleErrors[field] = allErrors[field];
  }

  const touch = (field: FieldName) => setTouched((prev) => new Set(prev).add(field));

  const handleChoose = async () => {
    const dir = await chooseDirectory();
    if (dir !== null) setValues((prev) => ({ ...prev, outputDir: dir }));
    touch("outputDir");
  };

  return (
    <PrepareClipForm
      values={values}
      errors={visibleErrors}
      canSubmit={Object.keys(allErrors).length === 0}
      onChange={(field, value) => setValues((prev) => ({ ...prev, [field]: value }))}
      onBlur={touch}
      onChooseDirectory={() => void handleChoose()}
      onSubmit={() => {
        if (Object.keys(allErrors).length === 0) {
          onSubmit(buildRequest(values, crypto.randomUUID()));
        }
      }}
    />
  );
}
