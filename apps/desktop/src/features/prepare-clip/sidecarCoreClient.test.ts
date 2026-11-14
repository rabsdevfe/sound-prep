import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PrepareClipRequest } from "../../ipc/types.generated";
import { createSidecarCoreClient, type SidecarHandlers, type SidecarProcess } from "./sidecarCoreClient";

const request = (id: string): PrepareClipRequest => ({
  v: 1,
  id,
  type: "prepare_clip",
  params: {
    url: "https://www.youtube.com/watch?v=abc",
    title: "Song",
    output_dir: "/tmp/out",
    start: "0:10",
    end: "0:20",
  },
});

const line = (value: unknown) => JSON.stringify(value);
const progress = (id: string, percent = 10) => ({ v: 1, id, type: "progress", stage: "downloading", percent });
const result = (id: string) => ({
  v: 1,
  id,
  type: "result",
  folder: "/tmp/out/Song",
  full_track: "/tmp/out/Song/Song.mp3",
  clip: "/tmp/out/Song/Song - clip.mp3",
});
const coreError = (id: string | null) => ({ v: 1, id, type: "error", code: "download_failed", message: "boom" });

/** Fake sidecar: records spawns and writes, lets tests push stdout and close it. */
function harness() {
  const writes: string[] = [];
  const spawns: SidecarHandlers[] = [];
  const state = { failSpawn: null as Error | null, failWrite: null as Error | null, delay: null as Promise<void> | null };
  const spawn = vi.fn(async (handlers: SidecarHandlers): Promise<SidecarProcess> => {
    spawns.push(handlers);
    if (state.delay) await state.delay;
    if (state.failSpawn) throw state.failSpawn;
    return {
      write: async (data) => {
        if (state.failWrite) throw state.failWrite;
        writes.push(data);
      },
    };
  });
  const client = createSidecarCoreClient({ spawn });
  const sent = () => writes.map((w) => JSON.parse(w));
  const last = () => spawns[spawns.length - 1]!;
  return { client, spawn, writes, sent, state, last };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("createSidecarCoreClient", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("writes the request as exactly one newline-terminated line", async () => {
    const h = harness();
    const job = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    expect(h.writes).toHaveLength(1);
    expect(h.writes[0]!.endsWith("\n")).toBe(true);
    expect(h.writes[0]!.slice(0, -1)).not.toContain("\n");
    expect(h.sent()[0]).toEqual(request("a"));
    h.last().onStdout(line(result("a")));
    await job;
  });

  it("forwards progress and resolves with the result", async () => {
    const h = harness();
    const onProgress = vi.fn();
    const job = h.client.prepareClip(request("a"), onProgress, new AbortController().signal);
    await tick();
    h.last().onStdout(line(progress("a", 40)));
    h.last().onStdout(line(result("a")));
    await expect(job).resolves.toEqual(result("a"));
    expect(onProgress).toHaveBeenCalledTimes(1);
    expect(onProgress).toHaveBeenCalledWith(progress("a", 40));
  });

  it("resolves with the core's error outcome", async () => {
    const h = harness();
    const job = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onStdout(line(coreError("a")));
    await expect(job).resolves.toEqual(coreError("a"));
  });

  it("routes interleaved messages by id", async () => {
    const h = harness();
    const pa = vi.fn();
    const pb = vi.fn();
    const a = h.client.prepareClip(request("a"), pa, new AbortController().signal);
    const b = h.client.prepareClip(request("b"), pb, new AbortController().signal);
    await tick();
    h.last().onStdout(line(progress("b", 1)));
    h.last().onStdout(line(progress("a", 2)));
    h.last().onStdout(line(result("b")));
    h.last().onStdout(line(coreError("a")));
    await expect(b).resolves.toEqual(result("b"));
    await expect(a).resolves.toEqual(coreError("a"));
    expect(pa).toHaveBeenCalledWith(progress("a", 2));
    expect(pb).toHaveBeenCalledWith(progress("b", 1));
    expect(pa).toHaveBeenCalledTimes(1);
    expect(pb).toHaveBeenCalledTimes(1);
  });

  it("reuses one process across jobs", async () => {
    const h = harness();
    const first = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onStdout(line(result("a")));
    await first;
    const second = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onStdout(line(result("b")));
    await second;
    expect(h.spawn).toHaveBeenCalledTimes(1);
    expect(h.writes).toHaveLength(2);
  });

  it("spawns lazily and once for concurrent first jobs, tolerating a slow spawn", async () => {
    const h = harness();
    expect(h.spawn).not.toHaveBeenCalled();
    let release!: () => void;
    h.state.delay = new Promise<void>((r) => (release = r));
    const a = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    const b = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await new Promise((r) => setTimeout(r, 30));
    expect(h.writes).toHaveLength(0);
    release();
    await tick();
    expect(h.spawn).toHaveBeenCalledTimes(1);
    expect(h.writes).toHaveLength(2);
    h.last().onStdout(line(result("a")));
    h.last().onStdout(line(result("b")));
    await Promise.all([a, b]);
  });

  it("ignores garbage, invalid, wrong-direction and unknown-id lines", async () => {
    const h = harness();
    const onProgress = vi.fn();
    const job = h.client.prepareClip(request("a"), onProgress, new AbortController().signal);
    await tick();
    const out = h.last().onStdout;
    out("not json");
    out("");
    out(line({ v: 1, id: "a", type: "result" })); // missing fields
    out(line({ v: 2, id: "a", type: "progress", stage: "cutting" }));
    out(line(request("a"))); // wrong direction
    out(line(progress("zzz")));
    out(line(result("zzz")));
    expect(onProgress).not.toHaveBeenCalled();
    let settled = false;
    void job.then(() => (settled = true));
    await tick();
    expect(settled).toBe(false);
    out(line(result("a")));
    await expect(job).resolves.toEqual(result("a"));
  });

  it("handles several lines in one chunk and keeps going if a listener throws", async () => {
    const h = harness();
    const onProgress = vi.fn(() => {
      throw new Error("listener bug");
    });
    const job = h.client.prepareClip(request("a"), onProgress, new AbortController().signal);
    await tick();
    h.last().onStdout(`${line(progress("a"))}\n${line(result("a"))}`);
    await expect(job).resolves.toEqual(result("a"));
    expect(onProgress).toHaveBeenCalledTimes(1);
  });

  it("rejects without spawning or writing when already aborted", async () => {
    const h = harness();
    const controller = new AbortController();
    controller.abort(new Error("stop"));
    await expect(h.client.prepareClip(request("a"), vi.fn(), controller.signal)).rejects.toThrow("stop");
    expect(h.spawn).not.toHaveBeenCalled();
  });

  it("aborting during a job rejects and silences later events, without breaking other jobs", async () => {
    const h = harness();
    const pa = vi.fn();
    const controller = new AbortController();
    const a = h.client.prepareClip(request("a"), pa, controller.signal);
    const b = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await tick();
    controller.abort(new Error("stop"));
    await expect(a).rejects.toThrow("stop");
    h.last().onStdout(line(progress("a")));
    h.last().onStdout(line(result("a")));
    expect(pa).not.toHaveBeenCalled();
    h.last().onStdout(line(result("b")));
    await expect(b).resolves.toEqual(result("b"));
  });

  it("aborting while the sidecar is still starting never sends the request", async () => {
    const h = harness();
    let release!: () => void;
    h.state.delay = new Promise<void>((r) => (release = r));
    const controller = new AbortController();
    const job = h.client.prepareClip(request("a"), vi.fn(), controller.signal);
    await tick();
    controller.abort(new Error("stop"));
    await expect(job).rejects.toThrow("stop");
    release();
    await tick();
    expect(h.writes).toHaveLength(0);
  });

  it("turns a spawn failure into an error outcome and retries on the next job", async () => {
    const h = harness();
    h.state.failSpawn = new Error("denied");
    const outcome = await h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    expect(outcome).toMatchObject({ id: "a", type: "error", code: "internal_error" });
    expect((outcome as { message: string }).message).toContain("denied");
    h.state.failSpawn = null;
    const job = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await tick();
    expect(h.spawn).toHaveBeenCalledTimes(2);
    h.last().onStdout(line(result("b")));
    await expect(job).resolves.toEqual(result("b"));
  });

  it("fails every in-flight job when the process closes mid-job, then respawns", async () => {
    const h = harness();
    const a = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    const b = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onClose();
    await expect(a).resolves.toMatchObject({ id: "a", type: "error", code: "internal_error" });
    await expect(b).resolves.toMatchObject({ id: "b", type: "error", code: "internal_error" });
    const c = h.client.prepareClip(request("c"), vi.fn(), new AbortController().signal);
    await tick();
    expect(h.spawn).toHaveBeenCalledTimes(2);
    h.last().onStdout(line(result("c")));
    await expect(c).resolves.toEqual(result("c"));
  });

  it("does not let a stale process close affect the new process", async () => {
    const h = harness();
    const a = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    const oldHandlers = h.last();
    oldHandlers.onClose();
    await a;
    const b = h.client.prepareClip(request("b"), vi.fn(), new AbortController().signal);
    await tick();
    oldHandlers.onClose();
    h.last().onStdout(line(result("b")));
    await expect(b).resolves.toEqual(result("b"));
    expect(h.spawn).toHaveBeenCalledTimes(2);
  });

  it("fails jobs when the process closes during startup", async () => {
    const h = harness();
    let release!: () => void;
    h.state.delay = new Promise<void>((r) => (release = r));
    const job = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onClose();
    release();
    await expect(job).resolves.toMatchObject({ id: "a", type: "error", code: "internal_error" });
  });

  it("fails in-flight jobs on an uncorrelated (null id) core error", async () => {
    const h = harness();
    const job = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onStdout(line(coreError(null)));
    await expect(job).resolves.toMatchObject({ id: "a", type: "error", code: "internal_error" });
  });

  it("fails in-flight jobs on a stream error from the plugin", async () => {
    const h = harness();
    const job = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onError("read failed");
    await expect(job).resolves.toMatchObject({ id: "a", type: "error", code: "internal_error" });
  });

  it("turns a failed stdin write into an error outcome", async () => {
    const h = harness();
    h.state.failWrite = new Error("broken pipe");
    const outcome = await h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    expect(outcome).toMatchObject({ id: "a", type: "error", code: "internal_error" });
  });

  it("refuses an id reused after abort until the core's final message for it arrives", async () => {
    const h = harness();
    const controller = new AbortController();
    const old = h.client.prepareClip(request("a"), vi.fn(), controller.signal);
    await tick();
    controller.abort(new Error("stop"));
    await expect(old).rejects.toThrow("stop");
    const onProgress = vi.fn();
    const reused = await h.client.prepareClip(request("a"), onProgress, new AbortController().signal);
    expect(reused).toMatchObject({ id: "a", type: "error", code: "internal_error" });
    expect(h.writes).toHaveLength(1);
    h.last().onStdout(line(progress("a")));
    h.last().onStdout(line(result("a"))); // the aborted job's terminal message frees the id
    expect(onProgress).not.toHaveBeenCalled();
    const again = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    expect(h.writes).toHaveLength(2);
    h.last().onStdout(line(result("a")));
    await expect(again).resolves.toEqual(result("a"));
  });

  it("frees owed ids when the process closes", async () => {
    const h = harness();
    const controller = new AbortController();
    const old = h.client.prepareClip(request("a"), vi.fn(), controller.signal);
    await tick();
    controller.abort(new Error("stop"));
    await expect(old).rejects.toThrow("stop");
    h.last().onClose();
    const next = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    h.last().onStdout(line(result("a")));
    await expect(next).resolves.toEqual(result("a"));
  });

  it("rejects a duplicate in-flight id without disturbing the original job", async () => {
    const h = harness();
    const a = h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    await tick();
    const dup = await h.client.prepareClip(request("a"), vi.fn(), new AbortController().signal);
    expect(dup).toMatchObject({ id: "a", type: "error", code: "internal_error" });
    h.last().onStdout(line(result("a")));
    await expect(a).resolves.toEqual(result("a"));
  });
});
