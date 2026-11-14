import { describe, expect, it } from "vitest";
import { createLocalStorageDirectoryStore } from "./localStorageDirectoryStore";

describe("localStorage directory store", () => {
  it("returns null when nothing was saved", () => {
    expect(createLocalStorageDirectoryStore(window.localStorage).load()).toBeNull();
  });

  it("remembers a saved directory across store instances", () => {
    createLocalStorageDirectoryStore(window.localStorage).save("/Users/me/Music");
    expect(createLocalStorageDirectoryStore(window.localStorage).load()).toBe("/Users/me/Music");
    window.localStorage.clear();
  });

  it("survives a storage that throws", () => {
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    } as unknown as Storage;
    const store = createLocalStorageDirectoryStore(broken);
    expect(() => store.save("/x")).not.toThrow();
    expect(store.load()).toBeNull();
  });
});
