import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobStatus } from "./JobStatus";
import { ERROR_MESSAGES, SLOW_START_HINT, type JobState } from "./jobState";

const result = {
  v: 1,
  id: "job-1",
  type: "result",
  folder: "/Users/me/Music/My song",
  full_track: "/Users/me/Music/My song/full.mp3",
  clip: "/Users/me/Music/My song/clip.mp3",
} as const;

const show = (state: JobState) => render(<JobStatus state={state} />);

describe("JobStatus presentation", () => {
  it("renders nothing while idle", () => {
    const { container } = show({ status: "idle" });
    expect(container).toBeEmptyDOMElement();
  });

  it("names the running stage and shows the percent when known", () => {
    show({ status: "running", stage: "downloading", percent: 41.6 });
    expect(screen.getByText("Downloading the track")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Downloading" })).toHaveValue(41.6);
  });

  it("shows an indeterminate bar and no percent before progress is known", () => {
    show({ status: "running", stage: "starting" });
    expect(screen.getByText("Starting the audio engine")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Starting" })).not.toHaveAttribute("value");
    expect(screen.queryByText(SLOW_START_HINT)).not.toBeInTheDocument();
  });

  it("shows the slow-start hint only while starting and slow", () => {
    const { rerender } = show({ status: "running", stage: "starting", slow: true });
    expect(screen.getByText(SLOW_START_HINT)).toBeInTheDocument();
    expect(screen.getAllByText(/audio engine/)).toHaveLength(1); // the title is not repeated
    rerender(<JobStatus state={{ status: "running", stage: "cutting", slow: true }} />);
    expect(screen.queryByText(SLOW_START_HINT)).not.toBeInTheDocument();
  });

  it("lists the folder, full track and clip as labelled rows on success", () => {
    show({ status: "success", result });
    expect(screen.getByText("Clip ready")).toBeInTheDocument();
    const rows = [
      ["Folder", result.folder],
      ["Full track", result.full_track],
      ["Clip", result.clip],
    ];
    for (const [label, path] of rows) {
      expect(screen.getByText(label).nextElementSibling).toHaveTextContent(path);
    }
  });

  it("lists the stems instead of a clip when the result carries stems", () => {
    const base = { v: 1, id: "job-1", type: "result", folder: result.folder, full_track: result.full_track } as const;
    const stems = {
      drums: "/m/drums.mp3",
      bass: "/m/bass.mp3",
      vocals: "/m/vocals.mp3",
      guitar: "/m/guitar.mp3",
      other: "/m/other.mp3",
    };
    show({ status: "success", result: { ...base, stems } });
    expect(screen.getByText("Stems ready")).toBeInTheDocument();
    expect(screen.queryByText("Clip")).not.toBeInTheDocument();
    for (const [name, path] of Object.entries(stems)) {
      expect(screen.getByText(`Stem: ${name}`).nextElementSibling).toHaveTextContent(path);
    }
  });

  it("names the separating stage", () => {
    show({ status: "running", stage: "separating", percent: 30 });
    expect(screen.getByText("Separating the stems")).toBeInTheDocument();
  });

  it("renders an error as a single alert with the human message", () => {
    show({ status: "error", code: "download_failed" });
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_MESSAGES.download_failed);
  });
});
