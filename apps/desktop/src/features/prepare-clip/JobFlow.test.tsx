/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ErrorCode, ProgressEvent } from "../../ipc/types.generated";
import type { CoreClient } from "./coreClient";
import { createFakeCoreClient } from "./fakeCoreClient";
import { ERROR_MESSAGES } from "./jobState";
import { PrepareClipContainer } from "./PrepareClipContainer";

const store = { load: () => "/Users/me/Music", save: vi.fn() };
const picker = { pick: vi.fn().mockResolvedValue("/Volumes/Other") };

function renderScreen(client: CoreClient) {
  return renderScreenView(client);
}

function renderScreenView(client: CoreClient) {
  const view = render(<PrepareClipContainer picker={picker} store={store} client={client} />);
  fireEvent.change(screen.getByLabelText("YouTube URL"), {
    target: { value: "https://youtu.be/abc" },
  });
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "My song" } });
  fireEvent.change(screen.getByLabelText("Start"), { target: { value: "0:10" } });
  fireEvent.change(screen.getByLabelText("End"), { target: { value: "1:30" } });
  fireEvent.click(screen.getByRole("button", { name: "Prepare clip" }));
  return view;
}

const schema = JSON.parse(
  readFileSync(join(process.cwd(), "../../contracts/ipc.schema.json"), "utf8"),
);
const CONTRACT_ERROR_CODES: ErrorCode[] = schema.$defs.ErrorCode.enum;

type Outcome = Awaited<ReturnType<CoreClient["prepareClip"]>>;

/** A client whose events the test drives by hand. */
function manualClient() {
  const calls: { id: string; signal: AbortSignal }[] = [];
  let emit: (event: ProgressEvent) => void = () => {};
  let finish: (outcome: Outcome) => void = () => {};
  const client: CoreClient = {
    prepareClip: (request, onProgress, signal) => {
      calls.push({ id: request.id, signal });
      emit = onProgress;
      return new Promise((resolve) => (finish = resolve));
    },
  };
  const progress = (partial: Partial<ProgressEvent> = {}) =>
    emit({ v: 1, id: calls[0].id, type: "progress", stage: "downloading", ...partial });
  const result = (id = calls[0].id): Outcome => ({
    v: 1,
    id,
    type: "result",
    folder: "/Users/me/Music/My song",
    full_track: "/Users/me/Music/My song/full.mp3",
    clip: "/Users/me/Music/My song/clip.mp3",
  });
  return { client, calls, progress, finish: (o: Outcome) => finish(o), result };
}

describe("prepare-clip job states", () => {
  it("is idle before submitting", () => {
    render(<PrepareClipContainer picker={picker} store={store} client={manualClient().client} />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows running stage and percent, then success with the output paths", async () => {
    const core = manualClient();
    renderScreen(core.client);
    expect(screen.getByRole("status")).toHaveTextContent("Starting…");
    const submit = screen.getByRole("button", { name: "Prepare clip" });
    expect(submit).toHaveAttribute("aria-disabled", "true");
    expect(submit).toBeEnabled();

    const live = screen.getByRole("status");
    act(() => core.progress({ percent: 42 }));
    expect(live).toHaveTextContent("Downloading…");
    expect(screen.getByRole("progressbar", { name: "Downloading" })).toHaveValue(42);
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(live).not.toHaveTextContent("42");

    act(() => core.progress({ percent: 60 }));
    expect(screen.getByRole("status")).toBe(live); // one persistent live region
    expect(live).toHaveTextContent(/^Downloading…$/); // percent changes are not announced
    expect(screen.getByRole("progressbar")).toHaveValue(60);

    act(() => core.progress({ stage: "cutting", percent: undefined }));
    expect(live).toHaveTextContent("Cutting…");

    await act(async () => core.finish(core.result()));
    expect(live).toHaveTextContent("Done. Your files are ready.");
    expect(live).toBeInTheDocument();
    for (const path of [
      "/Users/me/Music/My song/clip.mp3",
      "/Users/me/Music/My song/full.mp3",
      "/Users/me/Music/My song",
    ]) {
      const element = screen.getByText(path);
      expect(live).not.toContainElement(element);
    }
    expect(screen.getByRole("button", { name: "Prepare clip" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it("keeps keyboard focus on the submit button while running", async () => {
    const core = manualClient();
    renderScreen(core.client);
    const submit = screen.getByRole("button", { name: "Prepare clip" });
    submit.focus();
    await screen.findByText("Starting…");
    expect(submit).toHaveFocus();
  });

  it("drops progress with a foreign id", async () => {
    const core = manualClient();
    renderScreen(core.client);
    await screen.findByText("Starting…");
    act(() => core.progress({ id: "someone-else", percent: 90 }));
    expect(screen.getByRole("status")).toHaveTextContent("Starting…");
    expect(screen.getByRole("progressbar")).not.toHaveValue(90);
  });

  it("drops progress that arrives after the result", async () => {
    const core = manualClient();
    renderScreen(core.client);
    await screen.findByText("Starting…");
    await act(async () => core.finish(core.result()));
    act(() => core.progress({ percent: 10 }));
    expect(screen.queryByText(/Downloading/)).not.toBeInTheDocument();
    expect(screen.getByText(/Done\./)).toBeInTheDocument();
  });

  it("treats a result for another request as an internal error", async () => {
    const core = manualClient();
    renderScreen(core.client);
    await screen.findByText("Starting…");
    await act(async () => core.finish(core.result("someone-else")));
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_MESSAGES.internal_error);
  });

  it("starts a single job for two submits in the same tick", () => {
    const core = manualClient();
    const { container } = render(
      <PrepareClipContainer picker={picker} store={store} client={core.client} />,
    );
    fireEvent.change(screen.getByLabelText("YouTube URL"), {
      target: { value: "https://youtu.be/abc" },
    });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "My song" } });
    fireEvent.change(screen.getByLabelText("Start"), { target: { value: "0:10" } });
    fireEvent.change(screen.getByLabelText("End"), { target: { value: "1:30" } });
    const form = container.querySelector("form")!;
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    expect(core.calls).toHaveLength(1);
  });

  it("cancels the job on unmount and ignores later events", async () => {
    const core = manualClient();
    const view = renderScreenView(core.client);
    await screen.findByText("Starting…");
    view.unmount();
    expect(core.calls[0].signal.aborted).toBe(true);
    expect(() => {
      core.progress({ percent: 50 });
      core.finish(core.result());
    }).not.toThrow();
  });

  it("does not let a settled run's events overwrite a newer run", async () => {
    const runs: { id: string; emit: (e: ProgressEvent) => void; finish: (o: Outcome) => void }[] =
      [];
    const client: CoreClient = {
      prepareClip: (request, emit) =>
        new Promise((finish) => runs.push({ id: request.id, emit, finish })),
    };
    renderScreen(client);
    await screen.findByText("Starting…");
    await act(async () =>
      runs[0].finish({ v: 1, id: runs[0].id, type: "error", code: "cut_failed", message: "m" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Prepare clip" }));
    expect(runs).toHaveLength(2);
    expect(runs[1].id).not.toBe(runs[0].id);
    act(() => runs[0].emit({ v: 1, id: runs[0].id, type: "progress", stage: "cutting" }));
    expect(screen.getByRole("status")).toHaveTextContent("Starting…");
  });

  it("completes a full run with the fake client", async () => {
    renderScreen(createFakeCoreClient({ stepDelayMs: 0 }));
    expect(await screen.findByText(/Done\./)).toBeInTheDocument();
    expect(screen.getByText("/Users/me/Music/My song/My song - clip.mp3")).toBeInTheDocument();
  });

  it("has a message for every error code in the contract", () => {
    expect(CONTRACT_ERROR_CODES.length).toBeGreaterThan(0);
    for (const code of CONTRACT_ERROR_CODES) {
      expect(ERROR_MESSAGES[code], code).toBeTruthy();
    }
    expect(Object.keys(ERROR_MESSAGES).sort()).toEqual([...CONTRACT_ERROR_CODES].sort());
  });

  it.each(CONTRACT_ERROR_CODES)("shows a human message for %s", async (code) => {
    renderScreen(createFakeCoreClient({ outcome: code, stepDelayMs: 0 }));
    const alert = await screen.findByText(ERROR_MESSAGES[code]);
    expect(alert).toHaveAttribute("role", "alert");
    expect(screen.queryByText(/Simulated/)).not.toBeInTheDocument();
  });

  it("shows an internal error when the client itself fails", async () => {
    renderScreen({ prepareClip: () => Promise.reject(new Error("pipe closed")) });
    expect(await screen.findByText(ERROR_MESSAGES.internal_error)).toBeInTheDocument();
  });

  it("shows a single alert after an error", async () => {
    renderScreen(createFakeCoreClient({ outcome: "output_dir_unavailable", stepDelayMs: 0 }));
    await screen.findByText(ERROR_MESSAGES.output_dir_unavailable);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_MESSAGES.output_dir_unavailable);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("lets the user re-pick after output_dir_unavailable, resubmit and succeed", async () => {
    const failing = createFakeCoreClient({ outcome: "output_dir_unavailable", stepDelayMs: 0 });
    const working = createFakeCoreClient({ stepDelayMs: 0 });
    const used: string[] = [];
    const client: CoreClient = {
      prepareClip: (request, onProgress, signal) => {
        used.push(request.params.output_dir);
        return (used.length === 1 ? failing : working).prepareClip(request, onProgress, signal);
      },
    };
    renderScreen(client);
    await screen.findByText(ERROR_MESSAGES.output_dir_unavailable);
    const dir = screen.getByLabelText("Output directory");
    expect(dir).toBeInvalid();
    expect(dir).toHaveAccessibleDescription("Choose another directory.");

    fireEvent.click(screen.getByRole("button", { name: "Choose…" }));
    await waitFor(() => expect(dir).toBeValid());
    expect(dir).toHaveValue("/Volumes/Other");

    fireEvent.click(screen.getByRole("button", { name: "Prepare clip" }));
    expect(await screen.findByText(/Done\./)).toBeInTheDocument();
    expect(used).toEqual(["/Users/me/Music", "/Volumes/Other"]);
    expect(screen.queryByText(ERROR_MESSAGES.output_dir_unavailable)).not.toBeInTheDocument();
  });
});

describe("fake core client", () => {
  it("emits contract-valid events", async () => {
    const { validateMessage } = await import("../../ipc/messages");
    const events: unknown[] = [];
    const outcome = await createFakeCoreClient({ stepDelayMs: 0 }).prepareClip(
      {
        v: 1,
        id: "r1",
        type: "prepare_clip",
        params: { url: "https://x.y/z", title: "T", output_dir: "/o", start: "0", end: "5" },
      },
      (e) => events.push(e),
      new AbortController().signal,
    );
    for (const message of [...events, outcome]) {
      expect(validateMessage(message).ok).toBe(true);
    }
  });

  it("honors cancellation", async () => {
    const controller = new AbortController();
    const pending = createFakeCoreClient({ stepDelayMs: 1000 }).prepareClip(
      {
        v: 1,
        id: "r1",
        type: "prepare_clip",
        params: { url: "https://x.y/z", title: "T", output_dir: "/o", start: "0", end: "5" },
      },
      () => {},
      controller.signal,
    );
    controller.abort();
    await expect(pending).rejects.toBeDefined();
  });
});
