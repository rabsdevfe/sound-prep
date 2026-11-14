import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { validateMessage } from "../../ipc/messages";
import { PrepareClipContainer } from "./PrepareClipContainer";
import type { CoreClient } from "./coreClient";
import type { DirectoryPicker, DirectoryStore } from "./ports";

function fakeStore(initial: string | null = null): DirectoryStore & { saved: string[] } {
  const saved: string[] = [];
  return { saved, load: () => initial, save: (dir) => void saved.push(dir) };
}

function setup(chosen: string | null = "/Users/me/Music", remembered: string | null = null) {
  const onSubmit = vi.fn<CoreClient["prepareClip"]>(() => new Promise(() => {}));
  const pick = vi.fn().mockResolvedValue(chosen);
  const picker: DirectoryPicker = { pick };
  const store = fakeStore(remembered);
  render(<PrepareClipContainer picker={picker} store={store} client={{ prepareClip: onSubmit }} />);
  return { onSubmit, pick, store };
}

const type = (label: string, value: string) => {
  const input = screen.getByLabelText(label);
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
};

const submit = () => screen.getByRole("button", { name: "Prepare clip" });

async function fillValid() {
  type("YouTube URL", "https://www.youtube.com/watch?v=abc");
  type("Title", "My song");
  fireEvent.click(screen.getByRole("button", { name: "Choose…" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Output directory")).toHaveValue("/Users/me/Music"),
  );
  type("Start", "0:10");
  type("End", "1:30");
}

describe("PrepareClipContainer validation", () => {
  it("shows the time format hint under the start and end fields", () => {
    setup();
    const hint = screen.getByText(/Times as 1:30/);
    expect(screen.getByLabelText("Start")).toHaveAccessibleDescription(hint.textContent!);
    expect(screen.getByLabelText("End")).toHaveAccessibleDescription(hint.textContent!);
    expect(screen.getByLabelText("Title")).not.toHaveAccessibleDescription(hint.textContent!);
  });

  it("starts with submit enabled and no errors shown", () => {
    setup();
    expect(submit()).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the output directory as read-only", () => {
    setup();
    expect(screen.getByLabelText("Output directory")).toHaveAttribute("readonly");
  });

  it.each(["", "not a url", "ftp://example.com/x", "https://exa mple.com"])(
    "rejects URL %j",
    (value) => {
      setup();
      type("YouTube URL", value);
      expect(screen.getByLabelText("YouTube URL")).toBeInvalid();
      expect(screen.getByLabelText("YouTube URL")).toHaveAccessibleDescription(/URL/);
    },
  );

  it("rejects an empty or whitespace-only title and one over 120 characters", () => {
    setup();
    type("Title", "   ");
    expect(screen.getByLabelText("Title")).toHaveAccessibleDescription("Enter a title.");
    type("Title", "a".repeat(121));
    expect(screen.getByLabelText("Title")).toHaveAccessibleDescription(/at most 120/);
    type("Title", "a".repeat(120));
    expect(screen.getByLabelText("Title")).toBeValid();
  });

  it.each(["", "abc", "1:75", "1:2", "-5"])("rejects time %j", (value) => {
    setup();
    type("Start", value);
    expect(screen.getByLabelText("Start")).toBeInvalid();
  });

  it.each(["30", "1:30", "1:00:05", "90:00"])("accepts time %j", (value) => {
    setup();
    type("Start", value);
    expect(screen.getByLabelText("Start")).toBeValid();
  });

  it("asks for a directory once Choose was used and cancelled", async () => {
    const { pick } = setup(null);
    fireEvent.click(screen.getByRole("button", { name: "Choose…" }));
    await waitFor(() => expect(pick).toHaveBeenCalled());
    expect(await screen.findByText("Choose an output directory.")).toBeInTheDocument();
  });

  it.each([
    ["1:30", "1:30"],
    ["2:00", "1:59"],
  ])("rejects end %s when start is %s (end must be after start)", (start, end) => {
    setup();
    type("Start", start);
    type("End", end);
    expect(screen.getByLabelText("End")).toHaveAccessibleDescription(/^End must be after start\./);
  });

  it("compares times numerically, not as text", () => {
    setup();
    type("Start", "9:00");
    type("End", "10:00");
    expect(screen.getByLabelText("End")).toBeValid();
  });
});

describe("PrepareClipContainer submit", () => {
  it("submits when every field is valid", async () => {
    const { onSubmit } = setup();
    await fillValid();
    fireEvent.click(submit());
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("submits a contract request with trimmed values", async () => {
    const { onSubmit } = setup();
    await fillValid();
    type("Title", "  Padded  ");
    fireEvent.click(submit());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      v: 1,
      type: "prepare_clip",
      params: {
        url: "https://www.youtube.com/watch?v=abc",
        title: "Padded",
        output_dir: "/Users/me/Music",
        start: "0:10",
        end: "1:30",
      },
    });
  });

  it("accepts padded URL and time values and sends them trimmed", async () => {
    const { onSubmit } = setup();
    await fillValid();
    type("YouTube URL", "  https://youtu.be/abc  ");
    type("Start", " 0:10 ");
    type("End", " 1:30 ");
    fireEvent.click(submit());
    expect(onSubmit.mock.calls[0][0].params).toMatchObject({
      url: "https://youtu.be/abc",
      start: "0:10",
      end: "1:30",
    });
  });

  it("sends a fresh contract-valid request id on every submit", async () => {
    const { onSubmit } = setup();
    await fillValid();
    fireEvent.click(submit());
    expect(validateMessage(onSubmit.mock.calls[0][0]).ok).toBe(true);
    expect(onSubmit.mock.calls[0][0].id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("does not submit an invalid form, shows every error and focuses the first invalid field", () => {
    const { onSubmit } = setup();
    type("Start", "0:10");
    type("End", "1:30");
    fireEvent.click(submit());
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("YouTube URL")).toBeInvalid();
    expect(screen.getByLabelText("Title")).toBeInvalid();
    expect(screen.getByLabelText("Output directory")).toBeInvalid();
    expect(screen.getByLabelText("YouTube URL")).toHaveFocus();
  });

  it("rejects a remembered relative directory", () => {
    const { onSubmit } = setup("/x", "relative/dir");
    fireEvent.click(submit());
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Output directory")).toBeInvalid();
  });
});

describe("PrepareClipContainer output directory", () => {
  const choose = () => fireEvent.click(screen.getByRole("button", { name: "Choose…" }));

  it("shows and remembers the picked directory", async () => {
    const { store } = setup("/Volumes/Audio");
    choose();
    await waitFor(() =>
      expect(screen.getByLabelText("Output directory")).toHaveValue("/Volumes/Audio"),
    );
    expect(store.saved).toEqual(["/Volumes/Audio"]);
  });

  it("keeps the current directory and saves nothing when the picker is cancelled", async () => {
    const { pick, store } = setup(null, "/Users/me/Music");
    choose();
    await waitFor(() => expect(pick).toHaveBeenCalled());
    expect(screen.getByLabelText("Output directory")).toHaveValue("/Users/me/Music");
    expect(store.saved).toEqual([]);
  });

  it("starts with the remembered directory", () => {
    setup("/x", "/Users/me/Music");
    expect(screen.getByLabelText("Output directory")).toHaveValue("/Users/me/Music");
  });

  it("starts empty when nothing is remembered", () => {
    setup();
    expect(screen.getByLabelText("Output directory")).toHaveValue("");
  });

  it("reports a rejected picker and recovers on the next attempt", async () => {
    const pick = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue("/ok");
    const store = fakeStore();
    render(
      <PrepareClipContainer picker={{ pick }} store={store} client={{ prepareClip: vi.fn() }} />,
    );
    choose();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not open the folder picker/);
    choose();
    await waitFor(() => expect(screen.getByLabelText("Output directory")).toHaveValue("/ok"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
