import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PrepareClipContainer } from "./PrepareClipContainer";

function setup(chosen: string | null = "/Users/me/Music") {
  const onSubmit = vi.fn();
  const chooseDirectory = vi.fn().mockResolvedValue(chosen);
  render(<PrepareClipContainer chooseDirectory={chooseDirectory} onSubmit={onSubmit} />);
  return { onSubmit, chooseDirectory };
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
  it("starts with submit disabled and no errors shown", () => {
    setup();
    expect(submit()).toBeDisabled();
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
    const { chooseDirectory } = setup(null);
    fireEvent.click(screen.getByRole("button", { name: "Choose…" }));
    await waitFor(() => expect(chooseDirectory).toHaveBeenCalled());
    expect(await screen.findByText("Choose an output directory.")).toBeInTheDocument();
  });

  it.each([
    ["1:30", "1:30"],
    ["2:00", "1:59"],
  ])("rejects end %s when start is %s (end must be after start)", (start, end) => {
    setup();
    type("Start", start);
    type("End", end);
    expect(screen.getByLabelText("End")).toHaveAccessibleDescription("End must be after start.");
  });

  it("compares times numerically, not as text", () => {
    setup();
    type("Start", "9:00");
    type("End", "10:00");
    expect(screen.getByLabelText("End")).toBeValid();
  });
});

describe("PrepareClipContainer submit", () => {
  it("enables submit only when every field is valid", async () => {
    setup();
    await fillValid();
    expect(submit()).toBeEnabled();
    type("End", "0:05");
    expect(submit()).toBeDisabled();
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

  it("does not submit an invalid form", () => {
    const { onSubmit } = setup();
    fireEvent.submit(submit().closest("form")!);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
