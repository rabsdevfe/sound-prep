import { createFakeCoreClient } from "./features/prepare-clip/fakeCoreClient";
import { createLocalStorageDirectoryStore } from "./features/prepare-clip/localStorageDirectoryStore";
import { PrepareClipContainer } from "./features/prepare-clip/PrepareClipContainer";
import { tauriDirectoryPicker } from "./features/prepare-clip/tauriDirectoryPicker";

const coreClient = createFakeCoreClient();
const directoryStore = createLocalStorageDirectoryStore();

function App() {
  return (
    <main>
      <h1>sound-prep</h1>
      <p>Prepare YouTube audio clips for MainStage.</p>
      {/* The real sidecar client replaces the fake in a later phase. */}
      <PrepareClipContainer
        picker={tauriDirectoryPicker}
        store={directoryStore}
        client={coreClient}
      />
    </main>
  );
}

export default App;
