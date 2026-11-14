import type { IpcMessage } from "./types.generated";
import { validate as compiled } from "./validate.generated";

export type { IpcMessage } from "./types.generated";

interface AjvError {
  instancePath: string;
  keyword: string;
  message?: string;
}

// The generated module is untyped (@ts-nocheck); give it the shape Ajv standalone code has.
const validate = compiled as unknown as ((data: unknown) => boolean) & {
  errors?: AjvError[] | null;
};

/** One validation problem, as reported by the precompiled validator. */
export interface IpcIssue {
  /** JSON pointer of the failing instance ("" is the message itself). */
  path: string;
  keyword: string;
  message: string;
}

export type ParseResult =
  | { ok: true; message: IpcMessage }
  | { ok: false; reason: "invalid_json" | "invalid_message"; issues: IpcIssue[] };

/** Validates an already-decoded value against the contract. */
export function validateMessage(value: unknown): ParseResult {
  if (validate(value)) {
    return { ok: true, message: value as IpcMessage };
  }
  const issues = (validate.errors ?? []).map((e) => ({
    path: e.instancePath,
    keyword: e.keyword,
    message: e.message ?? "",
  }));
  return { ok: false, reason: "invalid_message", issues };
}

/** Parses one incoming JSON line into a validated message. Never throws on bad input. */
export function parseLine(line: string): ParseResult {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch (error) {
    const message = error instanceof Error ? error.message : "invalid JSON";
    return { ok: false, reason: "invalid_json", issues: [{ path: "", keyword: "json", message }] };
  }
  return validateMessage(value);
}

/** Serializes an outgoing message to exactly one line, terminated by a single newline. */
export function serializeMessage(message: IpcMessage): string {
  return `${JSON.stringify(message)}\n`;
}
