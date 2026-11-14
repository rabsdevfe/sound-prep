import { PrepareClipContainer } from "./features/prepare-clip/PrepareClipContainer";

function App() {
  return (
    <main>
      <h1>sound-prep</h1>
      <p>Prepare YouTube audio clips for MainStage.</p>
      {/* Folder picker and job execution are wired in the following work units. */}
      <PrepareClipContainer chooseDirectory={() => Promise.resolve(null)} onSubmit={() => {}} />
    </main>
  );
}

export default App;
