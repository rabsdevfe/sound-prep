import { Command } from "@tauri-apps/plugin-shell";
import { parseLine, serializeMessage } from "../../ipc/messages";
import type {
  ErrorCode,
  ErrorMessage,
  PrepareClipRequest,
  ProgressEvent,
} from "../../ipc/types.generated";
import type { CoreClient, EngineUnavailable, JobOutcome } from "./coreClient";

/** Name of the sidecar as declared in `bundle.externalBin` and in the capability. */
export const SIDECAR_NAME = "binaries/core";

/** What the client needs from a running sidecar. */
export interface SidecarProcess {
  /** Writes one chunk to the sidecar's stdin. */
  write: (data: string) => Promise<void>;
}

export interface SidecarHandlers {
  /** One chunk of stdout. The shell plugin delivers one line per chunk, newline stripped. */
  onStdout: (chunk: string) => void;
  /** Non-fatal stream error reported by the plugin. */
  onError: (message: string) => void;
  /** The process ended (exit, crash or kill). */
  onClose: () => void;
}

/** Starts the sidecar and wires its events. Rejects when it cannot start. */
export type SpawnSidecar = (handlers: SidecarHandlers) => Promise<SidecarProcess>;

/**
 * Default spawner on top of the Tauri shell plugin. Only `spawn` and stdin writes are
 * permitted by the capability: there is no kill, so the process ends when its stdin closes
 * (app exit). It takes no arguments: the capability cannot restrict them, the core rejects argv.
 */
export const spawnSidecar: SpawnSidecar = async ({ onStdout, onError, onClose }) => {
  const command = Command.sidecar(SIDECAR_NAME);
  command.stdout.on("data", onStdout);
  // Drain stderr so the pipe can never fill and block the core. Its content is not used.
  command.stderr.on("data", () => {});
  command.on("error", onError);
  command.on("close", onClose);
  const child = await command.spawn();
  return { write: (data) => child.write(data) };
};

export interface SidecarCoreClientOptions {
  spawn?: SpawnSidecar;
}

interface Job {
  onProgress: (event: ProgressEvent) => void;
  settle: (outcome: JobOutcome) => void;
}

interface Session {
  process: SidecarProcess;
  jobs: Map<string, Job>;
  /**
   * Ids the core still owes a terminal message for. Aborted jobs stay here until it arrives,
   * so a reused id can never receive the old job's late messages.
   */
  owed: Set<string>;
  /**
   * True once the core sent any valid message: from then on an exit is a crash, not a failed
   * start.
   */
  answered: boolean;
}

const failure = (id: string, code: ErrorCode, message: string): ErrorMessage => ({
  v: 1,
  id,
  type: "error",
  code,
  message,
});

const engineUnavailable = (
  id: string,
  reason: EngineUnavailable["reason"],
  message: string,
): EngineUnavailable => ({ type: "engine_unavailable", id, reason, message });

const describe = (error: unknown) => (error instanceof Error ? error.message : String(error));

/**
 * `CoreClient` backed by ONE long-lived sidecar per app session, spawned on first use.
 *
 * - Every incoming line is validated against the IPC contract; invalid lines are dropped
 *   (never trusted, never fatal), as are messages for unknown ids and wrong-direction types.
 * - Aborting rejects the caller's promise and stops its events. The contract has no cancel
 *   message and the capability grants no kill, so the core finishes the job and its late
 *   messages are discarded.
 * - A sidecar that fails to start, exits, or reports an uncorrelated error ends the
 *   affected jobs with an `engine_unavailable` outcome (reason `start_failed` if it never
 *   answered, `stopped` after it did); other failures end them with `internal_error`; the next job spawns a fresh process.
 * - There is deliberately no spawn timeout: the first launch after an install can take ~12 s.
 */
export function createSidecarCoreClient({
  spawn = spawnSidecar,
}: SidecarCoreClientOptions = {}): CoreClient {
  let starting: Promise<Session> | null = null;
  let active: Session | null = null;

  const failAll = (session: Session, message: string, exited = false) => {
    session.owed.clear();
    const reason = session.answered ? "stopped" : "start_failed";
    for (const [id, job] of [...session.jobs]) {
      session.jobs.delete(id);
      job.settle(
        exited
          ? engineUnavailable(id, reason, message)
          : failure(id, "internal_error", message),
      );
    }
  };

  const handleLine = (session: Session, line: string) => {
    if (line.trim() === "") return;
    const parsed = parseLine(line);
    if (!parsed.ok) {
      console.warn(`Ignored invalid core message (${parsed.reason}).`);
      return;
    }
    const message = parsed.message;
    if (message.type === "prepare_clip") return; // wrong direction
    session.answered = true;
    if (message.type === "error" && message.id === null) {
      // The core could not tell which request failed: nothing can be correlated anymore.
      failAll(session, `Core error: ${message.message}`);
      return;
    }
    if (message.type !== "progress") session.owed.delete(message.id as string);
    const job = session.jobs.get(message.id as string);
    if (!job) return; // unknown, finished or aborted job
    if (message.type === "progress") {
      try {
        job.onProgress(message);
      } catch (error) {
        console.error("Progress listener failed.", error);
      }
      return;
    }
    session.jobs.delete(message.id as string);
    job.settle(message);
  };

  const start = (): Promise<Session> => {
    if (starting) return starting;
    const attempt = (async () => {
      const jobs = new Map<string, Job>();
      let session: Session | null = null;
      let closedEarly = false;
      const process = await spawn({
        onStdout: (chunk) => {
          if (!session) return;
          for (const line of chunk.split("\n")) handleLine(session, line);
        },
        // A stream error does not prove the process died (`close` reports that), so the process
        // is kept; but messages may have been lost, so in-flight jobs could wait forever.
        onError: (message) => {
          if (session) failAll(session, `Core stream error: ${message}`);
        },
        onClose: () => {
          if (!session) {
            closedEarly = true;
            return;
          }
          failAll(session, "The core process ended unexpectedly.", true);
          if (active === session) {
            active = null;
            starting = null;
          }
        },
      });
      if (closedEarly) throw new Error("the core process exited during startup");
      session = { process, jobs, owed: new Set(), answered: false };
      active = session;
      return session;
    })();
    starting = attempt;
    attempt.catch(() => {
      if (starting === attempt) starting = null;
    });
    return attempt;
  };

  return {
    prepareClip: async (request: PrepareClipRequest, onProgress, signal) => {
      const { id } = request;
      if (signal.aborted) throw signal.reason;

      return new Promise<JobOutcome>((resolve, reject) => {
        let session: Session | null = null;
        let registered = false;
        let done = false;

        const finish = (action: () => void) => {
          if (done) return;
          done = true;
          signal.removeEventListener("abort", onAbort);
          if (registered) session?.jobs.delete(id);
          action();
        };
        const onAbort = () => finish(() => reject(signal.reason));
        signal.addEventListener("abort", onAbort, { once: true });

        start().then(
          (started) => {
            if (done) return;
            session = started;
            if (session.owed.has(id)) {
              finish(() =>
                resolve(failure(id, "internal_error", "A job with this id is still running or owed a final message by the core.")),
              );
              return;
            }
            const current = session;
            registered = true;
            current.owed.add(id);
            current.jobs.set(id, {
              onProgress,
              settle: (outcome) => finish(() => resolve(outcome)),
            });
            current.process.write(serializeMessage(request)).catch((error: unknown) => {
              if (current.jobs.get(id)) {
                finish(() =>
                  resolve(
                    failure(id, "internal_error", `Could not send to the core: ${describe(error)}`),
                  ),
                );
              }
            });
          },
          (error: unknown) =>
            finish(() =>
              resolve(
                engineUnavailable(id, "start_failed", `Could not start the core: ${describe(error)}`),
              ),
            ),
        );
      });
    },
  };
}
