import { useState } from "react";
import type { PrepareClipRequest } from "../../ipc/types.generated";
import { PrepareClipForm } from "./PrepareClipForm";
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
  onSubmit: (request: PrepareClipRequest) => void;
}

export function PrepareClipContainer({ picker, store, onSubmit }: PrepareClipContainerProps) {
  const [values, setValues] = useState<FormValues>(() => ({
    ...EMPTY_VALUES,
    outputDir: store.load() ?? "",
  }));
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Set<FieldName>>(new Set());

  const allErrors = validateForm(values);
  const visibleErrors: FieldErrors = {};
  for (const field of touched) {
    if (allErrors[field]) visibleErrors[field] = allErrors[field];
  }

  if (pickerError) visibleErrors.outputDir = pickerError;

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
      store.save(dir);
    }
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
