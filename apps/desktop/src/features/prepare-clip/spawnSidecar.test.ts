import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const child = { write: vi.fn(async () => {}) };
  const listeners: Record<string, (arg: never) => void> = {};
  const command = {
    stdout: { on: vi.fn((e: string, l: (arg: never) => void) => void (listeners[`stdout:${e}`] = l)) },
    stderr: { on: vi.fn((e: string, l: (arg: never) => void) => void (listeners[`stderr:${e}`] = l)) },
    on: vi.fn((e: string, l: (arg: never) => void) => void (listeners[e] = l)),
    spawn: vi.fn(async () => child),
  };
  return { child, command, listeners, sidecar: vi.fn<(name: string) => typeof command>(() => command) };
});

vi.mock("@tauri-apps/plugin-shell", () => ({ Command: { sidecar: mocks.sidecar } }));

import { spawnSidecar } from "./sidecarCoreClient";

describe("spawnSidecar", () => {
  it("spawns only binaries/core without arguments and wires events and stdin", async () => {
    const handlers = { onStdout: vi.fn(), onError: vi.fn(), onClose: vi.fn() };
    const process = await spawnSidecar(handlers);
    expect(mocks.sidecar).toHaveBeenCalledWith("binaries/core");
    mocks.listeners["stdout:data"]!("x" as never);
    mocks.listeners["error"]!("e" as never);
    mocks.listeners["close"]!({ code: 1, signal: null } as never);
    expect(mocks.listeners["stderr:data"]).toBeTypeOf("function"); // drained
    expect(handlers.onStdout).toHaveBeenCalledWith("x");
    expect(handlers.onError).toHaveBeenCalledWith("e");
    expect(handlers.onClose).toHaveBeenCalled();
    await process.write("line\n");
    expect(mocks.child.write).toHaveBeenCalledWith("line\n");
  });
});
