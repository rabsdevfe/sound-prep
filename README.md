# sound-prep

macOS desktop app to prepare audio clips from YouTube tracks for live performance work in MainStage.

## Features

- Download a YouTube track as MP3.
- Cut a clip from a time range (`SS`, `MM:SS` or `HH:MM:SS`).
- Save both files into a configurable directory, grouped by title.

### Planned

- Compare two clips and report sound differences (EQ balance, loudness, dynamics, stereo width) to guide patch adjustments in MainStage.

## Stack

- **UI:** Tauri + React (TypeScript)
- **Core:** Python sidecar, hexagonal architecture (`yt-dlp`, `ffmpeg`, `librosa`)

## Status

Early setup. Not usable yet.

## License

[MIT](LICENSE)
