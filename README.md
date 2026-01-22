# SafeKeeps Vault

Privacy-first, local-only video search across transcripts, visual content, and detected objects.

## Overview

SafeKeeps Vault is a desktop application that indexes your local video files and enables powerful multi-modal search:

- **Transcript Search**: Full-text search across speech transcribed by Whisper
- **Visual Search**: Semantic search using OpenCLIP embeddings
- **Object Detection**: Filter by detected objects using SSDLite MobileNetV3

All processing happens locally. Your videos never leave your machine.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Desktop Shell | Tauri 2 (Rust) |
| Frontend | React 19, TypeScript, Vite |
| Backend/Engine | Python 3.11+, FastAPI |
| Database | SQLite with FTS5 |
| Visual Search | FAISS |
| Speech Recognition | Whisper (base model) |
| Visual Embeddings | OpenCLIP (ViT-B-32) |
| Object Detection | SSDLite MobileNetV3 |

## Project Structure

```
gaze_v3/
├── app/                    # Tauri + React application
│   ├── src/               # React frontend
│   └── src-tauri/         # Rust backend
├── engine/                 # Python ML engine
│   └── src/engine/        # FastAPI application
├── contracts/             # API contracts (OpenAPI, WebSocket schemas)
├── scripts/               # Development and build scripts
└── docs/                  # Documentation
```

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** with pip
  - Download from [python.org](https://www.python.org/downloads/)
  - Verify: `python --version`
- **Node.js 18+** with npm
  - Download from [nodejs.org](https://nodejs.org/)
  - Verify: `node --version` and `npm --version`
- **Rust** (latest stable) with cargo
  - **Windows**: Download [rustup-init.exe](https://rustup.rs/) and run it
  - After installation, restart your terminal
  - Verify: `cargo --version` and `rustc --version`
  - Alternative: `choco install rust` (Chocolatey) or `scoop install rust` (Scoop)
- **FFmpeg** installed and in PATH
  - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use `choco install ffmpeg`
  - Verify: `ffmpeg -version`

## Development Setup

### 1. Clone and navigate to the project

```bash
cd gaze_v3
```

### 2. Install Python dependencies

```bash
cd engine
pip install -e .
cd ..
```

### 3. Install Node dependencies

```bash
cd app
npm install
cd ..
```

### 4. Run in development mode

**Windows (PowerShell):**
```powershell
.\scripts\dev.ps1
```

python -m engine.main --log-level DEBUG --port 48100

**macOS/Linux:**
```bash
./scripts/dev.sh
```

Or manually:

```bash
cd app
npm run tauri dev
```

## API Contract

The API contract is defined in `contracts/openapi.yaml`. Key endpoints:

- `GET /health` - Engine health status
- `POST /models` - Download ML models
- `GET /libraries` - List video libraries
- `POST /search` - Multi-modal search

## Architecture Decisions

See [GAZE_V3_ARCHITECTURE.md](./GAZE_V3_ARCHITECTURE.md) for detailed architecture documentation including:

- V2 post-mortem and lessons learned
- Contract-first development approach
- Explicit state machines for job management
- File fingerprinting for change detection

## License

MIT
# gaze_v3
# gaze_v3
