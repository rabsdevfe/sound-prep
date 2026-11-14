import type { DirectoryStore } from "./ports";

const KEY = "sound-prep.outputDir";

/** Persists the directory in the webview's localStorage; storage failures are non-fatal. */
export function createLocalStorageDirectoryStore(storage: Storage = localStorage): DirectoryStore {
  return {
    load: () => {
      try {
        return storage.getItem(KEY);
      } catch {
        return null;
      }
    },
    save: (dir) => {
      try {
        storage.setItem(KEY, dir);
      } catch {
        // Remembering the directory is a convenience; ignore storage errors.
      }
    },
  };
}
