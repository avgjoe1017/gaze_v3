# Gaze V3 Architecture

**Date:** 2026-01-20  
**Author:** Claude + Joe  
**Status:** Active Development (implementation snapshot)

---

## Executive Summary

Gaze V3 is a privacy-first, local-only photo and video library for families. It runs entirely on-device, does not upload media, and does not use cloud AI. The engine indexes files locally, stores metadata and derived artifacts, and supports opt-in face recognition. A metadata-only backup and restore path exists to preserve libraries and settings without exposing media files.

---

## Key Decisions vs V2

| Decision | V2 | V3 (current) |
|---|---|---|
| Desktop shell | Electron | Tauri 2.x |
| Media scope | Video only | Photos + videos (unified `media` table) |
| Face recognition | Not present | Optional and opt-in (InsightFace) |
| API contract | Implicit | OpenAPI spec maintained; client is handwritten |
| Packaging | Large bundle | Tauri sidecar for release, Python in dev |
| File tracking | Size + mtime | Fingerprint (size + head/tail hash) |
| Indexing stages | Implicit | Explicit stages per media type |

---

## Architecture Principles (Current)

1. **Privacy-first, local-only.** All processing is on-device. Network access is limited to explicit model downloads, and offline mode can block downloads entirely.
2. **Contract-aligned.** `contracts/openapi.yaml` is the reference. The app uses a handwritten client today; no generated client yet.
3. **Unified media model.** All files are represented in `media` with `media_type` and metadata. Videos also live in `videos` for video-specific fields and state.
4. **Explicit pipeline stages.** Video and photo indexing share a common state machine with media-specific stages.
5. **Resumable and consistent.** Processing state is stored in both `videos` and `media`, allowing resumption and UI visibility.
6. **Face recognition is opt-in.** It is disabled by default and only runs when explicitly enabled in settings.

---

## Technology Stack

### Desktop + Frontend
- **Tauri 2.x** desktop shell (sidecar in release, Python in dev)
- **React 19**, **TypeScript 5.6**, **Vite 6**
- **Zustand** for local app state
- **TanStack Query** present (limited usage today)

### Engine
- **Python 3.11+**
- **FastAPI** for HTTP and WebSocket
- **SQLite + FTS5** for metadata and transcript search
- **FAISS** for visual embedding search
- **Whisper** for transcription
- **OpenCLIP** for visual embeddings
- **SSDLite MobileNetV3** for object detection
- **InsightFace (optional)** for face detection and embeddings

### External Dependency
- **FFmpeg** (not bundled); required for video audio and frame extraction

---

## Repository Structure (Current)

```
gaze_v3/
├── contracts/
│   ├── openapi.yaml
│   └── ws-messages.json
│
├── app/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/               # apiClient, shared helpers
│   │   ├── stores/
│   │   ├── App.tsx
│   │   └── styles.css
│   ├── src-tauri/
│   │   └── src/
│   │       ├── engine.rs
│   │       └── main.rs
│   └── package.json
│
├── engine/
│   └── src/engine/
│       ├── api/               # backup, media, videos, faces, settings, etc.
│       ├── core/              # scanner, indexer, searcher
│       ├── db/                # SQLite schema and migrations
│       ├── ml/                # whisper, clip, detector, face_detector
│       ├── ws/                # websocket handler
│       └── utils/
│
├── scripts/
│   ├── dev.ps1
│   ├── build-engine.ps1
│   └── build-app.ps1
└── README.md
```

---

## Engine Lifecycle (Current)

1. Tauri starts the engine via `start_engine`.
2. A random port in `48100-48199` is chosen and a random bearer token is generated.
3. In dev, Python is spawned directly. In release, a sidecar binary is used (with Python fallback).
4. The frontend retrieves `port` and `token` via Tauri commands and uses `Authorization: Bearer <token>` for HTTP.
5. WebSocket auth uses the token as a query string (`/ws?token=...`).
6. `stop_engine` calls `/shutdown`, then kills the process if needed.

No lockfile or PID reuse exists yet.

---

## API Surface (Current)

The OpenAPI spec lives in `contracts/openapi.yaml`. The UI uses a handwritten client in `app/src/lib/apiClient.ts`.

Key endpoint groups:
- **Health:** `/health`, `/shutdown`
- **Models:** `/models`
- **Libraries:** `/libraries`, `/libraries/{id}`, `/libraries/{id}/scan`
- **Media:** `/media` (unified listing), `/videos` (video-only listing)
- **Search:** `/search`
- **Jobs:** `/jobs`, `/jobs/{id}`
- **Faces:** `/faces` and related person endpoints (when enabled)
- **Settings:** `/settings`
- **Backup:** `/backup/export`, `/backup/restore` (metadata only)
- **Misc:** `/stats`, `/logs`, `/assets`

---

## WebSocket (Current)

- URL: `ws://127.0.0.1:{port}/ws?token=...`
- Client sends `{ "type": "subscribe", "topics": ["*"] }`
- Messages include: `model_download_progress`, `model_download_complete`, `scan_progress`, `scan_complete`, `job_progress`, `job_complete`, `job_failed`, `heartbeat`, `pong`

---

## Indexing Pipeline

### Stage Lists
**Videos:**
```
EXTRACTING_AUDIO → TRANSCRIBING → EXTRACTING_FRAMES → EMBEDDING → DETECTING → DETECTING_FACES
```

**Photos:**
```
EXTRACTING_FRAMES → EMBEDDING → DETECTING → DETECTING_FACES
```

### Notes
- `DETECTING_FACES` only runs if `face_recognition_enabled` is true and InsightFace is available.
- Whisper, OpenCLIP, and detector stages gracefully skip if the model is missing.
- State and progress are stored in both `videos` and `media`.

---

## File Fingerprinting

Files are fingerprinted with a fast content signature:
- File size
- First 64 KB and last 64 KB hash

This enables reliable change detection without full-file hashing.

---

## Database Schema (Current)

Core tables:
- `libraries`
- `media` (unified photo + video)
- `media_metadata` (flexible key value)
- `videos` (video-specific fields + processing state)
- `video_metadata` (flexible key value)
- `transcript_segments`, `transcript_fts`
- `frames` (thumbnails + dominant colors)
- `detections`
- `faces`, `persons`
- `jobs`
- `settings`

Notes:
- For videos, `media_id == video_id`.
- `media_type` exists in both `media` and `videos`.
- Derived tables (`transcripts`, `frames`, `detections`, `faces`, `jobs`) can be rebuilt from source media.

---

## Model Management

**Required for models_ready:**
- `whisper-base`
- `openclip-vit-b-32`
- `ssdlite320-mobilenet-v3`

**Optional:**
- **InsightFace** (face detection and embeddings) when face recognition is enabled.

**Offline mode:**
- Settings allow `offline_mode` to block downloads.
- `/models` returns an error when offline.

---

## Backup and Restore (Metadata Only)

`/backup/export` includes:
- settings
- libraries
- media and media_metadata
- videos and video_metadata
- persons

`/backup/restore` supports:
- **merge** (preserve existing data, add new)
- **replace** (wipe tables and import, then clear derived tables)

Media files are never included.

---

## Security and Privacy

- Engine binds to `127.0.0.1` only.
- HTTP uses a per-session bearer token.
- WebSocket auth uses token query parameter.
- No telemetry, no analytics, no cloud upload.
- Face recognition is opt-in and disabled by default.

---

## Open Questions

1. Lockfile and engine reuse for multi-launch scenarios.
2. Packaging and signing pipeline for stable installers.
3. Search UX for mixed photo + video results.
4. FAISS scaling strategy (per-media shards vs merged index).

---

*End of V3 Architecture Document*
