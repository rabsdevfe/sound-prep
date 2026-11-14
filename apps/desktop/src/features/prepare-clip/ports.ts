/** Lets the user pick a folder. Resolves to the absolute path, or null when cancelled. */
export interface DirectoryPicker {
  pick: () => Promise<string | null>;
}

/** Remembers the last chosen output directory across launches. */
export interface DirectoryStore {
  load: () => string | null;
  save: (dir: string) => void;
}
