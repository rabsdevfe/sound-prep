import { open } from "@tauri-apps/plugin-dialog";
import type { DirectoryPicker } from "./ports";

/** Native macOS folder picker through the official Tauri dialog plugin. */
export const tauriDirectoryPicker: DirectoryPicker = {
  pick: async () => {
    const chosen = await open({
      directory: true,
      multiple: false,
      title: "Choose output directory",
    });
    return typeof chosen === "string" ? chosen : null;
  },
};
