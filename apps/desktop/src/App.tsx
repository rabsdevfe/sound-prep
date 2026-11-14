import { createLocalStorageDirectoryStore } from "./features/prepare-clip/localStorageDirectoryStore";
import { PrepareClipContainer } from "./features/prepare-clip/PrepareClipContainer";
import { createSidecarCoreClient } from "./features/prepare-clip/sidecarCoreClient";
import { tauriDirectoryPicker } from "./features/prepare-clip/tauriDirectoryPicker";

const coreClient = createSidecarCoreClient();
const directoryStore = createLocalStorageDirectoryStore();

function App() {
  return (
    <main>
      <h1>sound-prep</h1>
      <p>Prepare YouTube audio clips for MainStage.</p>
      <PrepareClipContainer
        picker={tauriDirectoryPicker}
        store={directoryStore}
        client={coreClient}
      />
    </main>
  );
}

export default App;
