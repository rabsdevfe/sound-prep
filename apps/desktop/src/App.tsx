import { createLocalStorageDirectoryStore } from "./features/prepare-clip/localStorageDirectoryStore";
import { PrepareClipContainer } from "./features/prepare-clip/PrepareClipContainer";
import { createSidecarCoreClient } from "./features/prepare-clip/sidecarCoreClient";
import { tauriDirectoryPicker } from "./features/prepare-clip/tauriDirectoryPicker";

const coreClient = createSidecarCoreClient();
const directoryStore = createLocalStorageDirectoryStore();

function App() {
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 p-5">
      <header>
        <h1 className="text-xl font-semibold">sound-prep</h1>
        <p className="text-muted">Prepare YouTube audio clips for MainStage.</p>
      </header>
      <PrepareClipContainer
        picker={tauriDirectoryPicker}
        store={directoryStore}
        client={coreClient}
      />
    </main>
  );
}

export default App;
