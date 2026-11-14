/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";
import { describe, expect, it } from "vitest";
import { parseLine, serializeMessage, validateMessage, type IpcMessage } from "./messages";

const FIXTURES = join(process.cwd(), "../../contracts/fixtures") // vitest runs from apps/desktop;
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, name), "utf8"));
const names = (dir: string): string[] => readdirSync(join(FIXTURES, dir)).sort();
const expectations: Record<string, { path: string; keyword: string }> = JSON.parse(
  readFileSync(join(FIXTURES, "invalid-expectations.json"), "utf8"),
);

describe("contract fixtures", () => {
  it("has fixtures and an expectation per invalid fixture", () => {
    expect(names("valid")).not.toHaveLength(0);
    expect(Object.keys(expectations).sort()).toEqual(names("invalid"));
  });

  it.each(names("valid"))("accepts valid/%s", (name) => {
    const result = validateMessage(load("valid", name));
    expect(result.ok).toBe(true);
  });

  it.each(names("invalid"))("rejects invalid/%s at the expected path and keyword", (name) => {
    const result = validateMessage(load("invalid", name));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    const expected = expectations[name];
    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: expected.path, keyword: expected.keyword }),
      ]),
    );
  });
});

describe("parseLine", () => {
  it("returns the typed message for a valid line", () => {
    const line = JSON.stringify(load("valid", "progress_downloading.json"));
    const result = parseLine(line);
    expect(result.ok && result.message.type).toBe("progress");
  });

  it.each(["", "not json", "{", "null", "42", "[]", '"text"'])("fails without throwing on %j", (line) => {
    const result = parseLine(line);
    expect(result.ok).toBe(false);
  });

  it("reports invalid_json versus invalid_message", () => {
    const bad = parseLine("{");
    const wrong = parseLine('{"type":"nope"}');
    expect(!bad.ok && bad.reason).toBe("invalid_json");
    expect(!wrong.ok && wrong.reason).toBe("invalid_message");
  });
});

describe("serializeMessage", () => {
  it.each(names("valid"))("round-trips valid/%s as a single line", (name) => {
    const message = load("valid", name) as IpcMessage;
    const line = serializeMessage(message);
    expect(line.endsWith("\n")).toBe(true);
    expect(line.slice(0, -1)).not.toContain("\n");
    const parsed = parseLine(line.trimEnd());
    expect(parsed.ok && parsed.message).toEqual(message);
  });

  it("keeps newlines inside strings escaped", () => {
    const message: IpcMessage = {
      v: 1,
      id: "a",
      type: "error",
      code: "internal_error",
      message: "line1\nline2",
    };
    const line = serializeMessage(message);
    expect(line.split("\n")).toHaveLength(2);
    expect(parseLine(line).ok).toBe(true);
  });
});
