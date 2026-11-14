import { createLocalStorageDirectoryStore } from "./features/prepare-clip/localStorageDirectoryStore";
import { PrepareClipContainer } from "./features/prepare-clip/PrepareClipContainer";
import { tauriDirectoryPicker } from "./features/prepare-clip/tauriDirectoryPicker";

const directoryStore = createLocalStorageDirectoryStore();

function App() {
  return (
    <main>
      <h1>sound-prep</h1>
      <p>Prepare YouTube audio clips for MainStage.</p>
      {/* Job execution is wired in the following work unit. */}
      <PrepareClipContainer
        picker={tauriDirectoryPicker}
        store={directoryStore}
        onSubmit={() => {}}
      />
    </main>
  );
}

export default App;
