# Gaze V3 Architecture

**Date:** 2026-01-18  
**Author:** Claude + Joe  
**Status:** Planning Phase

---

## Executive Summary

Gaze V3 is a ground-up rebuild of Gaze V2, informed by hard-won lessons from debugging infrastructure instead of shipping features. The core value proposition remains: **privacy-first, local-only video search** across transcripts, visual content, and detected objects.

**Key architectural changes from V2:**

| Decision | V2 | V3 |
|----------|----|----|
| Desktop shell | Electron (~150MB) | Tauri (~15MB) |
| ML backend | Python (same) | Python (same) |
| SSDLite | Optional/confused | Core (always installed) |
| API contract | Implicit, drifted | OpenAPI-first, generated clients |
| Packaging | Placeholder scripts | CI-built installers from week 2 |
| UI paths | Two (HomeVault + App.tsx) | One, wired end-to-end |
| Job states | Implicit stage progression | Explicit state machine |
| File tracking | Size + mtime only | Fingerprint (hash of head/tail) |

**Target:** Distributable product with signed installers for Windows, macOS, and Linux.

---

## V2 Post-Mortem: What Broke Momentum

Before defining V3, we must understand why V2 stalled at "almost working."

### The Debugging Tax

V2's progress logs reveal weeks spent on:

1. **Engine restart loops** — Health monitor killed engines before they finished starting. Fixed with a 15-second delay (band-aid, not cure).

2. **Preload sandbox errors** — `module not found: node:fs` because Electron's sandboxed renderer couldn't access Node APIs. Fixed by disabling sandbox entirely.

3. **CJS/ESM confusion** — Parallel `.ts` and `.cjs` files for Electron, with only CJS actually running. TypeScript could drift without anyone noticing.

4. **Stale lockfiles** — Crash leaves `engine.lock` on disk. Next launch fails with `ENGINE_ALREADY_RUNNING`. User must manually delete file from AppData.

5. **WebSocket auth mismatch** — Client sent token via query string, server only read headers. Progress events never arrived. Neither side threw a useful error.

6. **Two UIs** — `HomeVault.tsx` (beautiful, mock data) vs `App.tsx` (ugly, actually connected). The ship-ready UI wasn't wired; the wired UI wasn't shippable.

### Root Causes

| Symptom | Root Cause |
|---------|------------|
| Restart loops | No readiness probe; health monitor assumed instant startup |
| Sandbox errors | Electron's security model vs preload's Node requirements |
| CJS/ESM confusion | No single source of truth; runtime didn't match dev |
| Stale lockfiles | No cleanup on crash; no staleness detection on startup |
| WS auth mismatch | No shared contract; client and server implemented independently |
| Two UIs | Premature optimization (pretty design before plumbing worked) |

### The Lesson

**V2 failed because integration was deferred.** Each component worked in isolation but broke at the seams. V3 must wire end-to-end first, polish second.

---

## V3 Architecture Principles

### 1. Contract-First Development

Before writing code:
- Define OpenAPI 3.1 spec for all HTTP endpoints
- Define JSON Schema for all WebSocket messages
- Generate TypeScript client from OpenAPI spec
- Generate Python server stubs from OpenAPI spec (optional, for validation)

**No endpoint exists until it's in the contract.** Frontend and backend cannot drift.

### 2. One Path, End-to-End

V3 has exactly one UI. It may be ugly at first. It must be functional from day one:
- Start engine → Download models → Add folder → Index → Search → Play result

No mock data. No placeholder handlers. If a button exists, it works.

### 3. Packaging from Week 2

V3 CI produces signed installers by the end of week 2. This forces us to solve:
- Python bundling (PyInstaller or PyOxidizer)
- Tauri cross-compilation
- Code signing (Windows EV cert, macOS notarization)
- Clean-machine testing

If packaging breaks, we fix it immediately—not as a pre-launch scramble.

### 4. Explicit State Machines

V2's job progression was implicit (CAPTIONS done? start VISUAL). V3 uses explicit states:

```
QUEUED → EXTRACTING_AUDIO → TRANSCRIBING → EXTRACTING_FRAMES → 
EMBEDDING → DETECTING → DONE

On error: → FAILED (with stage + error code)
On cancel: → CANCELLED
```

Each stage is resumable. Crash recovery = "find videos not DONE, resume from last completed stage."

### 5. File Fingerprinting

V2 tracked size + mtime. V3 adds a content fingerprint:

```python
def fingerprint(path: Path) -> str:
    stat = path.stat()
    with open(path, 'rb') as f:
        head = f.read(65536)  # first 64KB
        f.seek(-65536, 2)
        tail = f.read(65536)  # last 64KB
    return hashlib.sha256(
        f"{stat.st_size}:{head}:{tail}".encode()
    ).hexdigest()[:16]
```

This catches:
- **NEW**: fingerprint not in DB
- **CHANGED**: fingerprint differs from DB
- **DELETED**: path in DB but file missing
- **RENAMED**: fingerprint matches but path differs

### 6. Detector is Core

No more "optional but recommended." The detector is required:
- Model download UI includes all three (Whisper, OpenCLIP, SSDLite)
- `/health` reports ready only when all three are present
- Indexing always runs all three stages
- No conditional logic for "detector might not be installed"

This simplifies health checks, UI gating, and documentation.

---

## Technology Stack

### Tauri (Desktop Shell)

**Why Tauri over Electron:**

| | Electron | Tauri |
|---|---|---|
| Bundle size | ~150MB | ~10-20MB |
| Runtime | Chromium + Node | System webview + Rust |
| IPC | preload.js bridge | Rust commands, typed |
| Maturity | 10+ years | Stable since 2022 |
| V2 pain points | Sandbox, CJS/ESM, preload | None (fresh start) |

Tauri's sidecar feature handles spawning the Python engine with proper lifecycle management.

**Tauri version:** 2.x (stable, cross-platform)

### Frontend (React)

- **React 19** — Latest stable
- **TypeScript 5.4+** — Strict mode, no `any`
- **Vite 6** — Fast builds, HMR
- **Zustand** — Simple state management (engine status, jobs, search results)
- **TanStack Query** — Server state, caching, retry logic

**No component library.** Custom components only. Keeps bundle small and avoids fighting framework opinions.

### Backend (Python Engine)

- **Python 3.11+** — Required for Whisper compatibility
- **FastAPI** — HTTP + WebSocket
- **SQLite + FTS5** — Metadata and transcript search
- **FAISS** — Visual embedding search
- **Whisper** — Speech recognition (base model)
- **OpenCLIP** — Visual embeddings (ViT-B-32)
- **Torchvision SSDLite MobileNetV3** — Object detection (permissive license)

**Python bundling:** PyInstaller for V3.0. Consider PyOxidizer later (Rust-native, pairs well with Tauri).

### FFmpeg

**Decision: Prompt, don't bundle (same as V2).**

- LGPL bundling is complex and platform-specific
- Most power users have FFmpeg installed
- Clear error message with install links if missing

Future: Investigate static LGPL builds for bundling in V3.1.

---

## Repository Structure

```
gaze_v3/
├── contracts/                    # API definitions (source of truth)
│   ├── openapi.yaml             # HTTP API spec
│   ├── ws-messages.json         # WebSocket message schemas
│   └── generate.sh              # Client/stub generation
│
├── app/                         # Tauri + React application
│   ├── src/                     # React frontend
│   │   ├── components/          # UI components
│   │   ├── hooks/               # Custom hooks
│   │   ├── api/                 # Generated API client + WebSocket
│   │   ├── stores/              # Zustand stores
│   │   └── App.tsx              # Root component
│   ├── src-tauri/               # Rust backend
│   │   ├── src/
│   │   │   ├── main.rs          # Entry point
│   │   │   ├── commands.rs      # Tauri commands
│   │   │   ├── engine.rs        # Engine lifecycle
│   │   │   └── lockfile.rs      # Lockfile management
│   │   ├── Cargo.toml
│   │   └── tauri.conf.json
│   ├── package.json
│   └── vite.config.ts
│
├── engine/                      # Python ML engine
│   ├── src/engine/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry
│   │   ├── api/                 # HTTP routes (generated stubs + impl)
│   │   │   ├── health.py
│   │   │   ├── libraries.py
│   │   │   ├── videos.py
│   │   │   ├── search.py
│   │   │   ├── models.py
│   │   │   └── jobs.py
│   │   ├── ws/                  # WebSocket handling
│   │   │   ├── handler.py
│   │   │   ├── auth.py
│   │   │   └── events.py
│   │   ├── core/                # Business logic
│   │   │   ├── lifecycle.py     # Startup, shutdown, lockfile
│   │   │   ├── scanner.py       # File discovery + fingerprinting
│   │   │   ├── indexer.py       # Job orchestration
│   │   │   └── searcher.py      # Multi-modal search
│   │   ├── ml/                  # ML model wrappers
│   │   │   ├── whisper.py
│   │   │   ├── clip.py
│   │   │   ├── detector.py
│   │   │   └── download.py
│   │   ├── db/                  # Database layer
│   │   │   ├── schema.sql
│   │   │   ├── connection.py
│   │   │   ├── migrations.py
│   │   │   └── consistency.py
│   │   └── utils/
│   │       ├── ffmpeg.py
│   │       ├── logging.py
│   │       └── paths.py
│   ├── tests/
│   │   ├── test_scanner.py
│   │   ├── test_indexer.py
│   │   ├── test_searcher.py
│   │   └── test_consistency.py
│   └── pyproject.toml
│
├── scripts/
│   ├── dev.sh                   # Start app + engine in dev mode
│   ├── build-engine.sh          # PyInstaller build
│   ├── build-app.sh             # Tauri build
│   └── package-all.sh           # Full release build
│
├── .github/
│   └── workflows/
│       ├── ci.yml               # Lint + test on PR
│       └── release.yml          # Build + sign + publish
│
├── docs/
│   ├── BUILD.md                 # Product spec (carried from V2)
│   ├── SECURITY.md              # Security requirements
│   └── DEVELOPMENT.md           # Dev setup guide
│
└── README.md
```

---

## API Contract

### HTTP Endpoints (OpenAPI)

```yaml
openapi: 3.1.0
info:
  title: Gaze Engine API
  version: 3.0.0

paths:
  /health:
    get:
      summary: Engine health and readiness
      responses:
        200:
          content:
            application/json:
              schema:
                type: object
                properties:
                  status: { type: string, enum: [starting, ready, error] }
                  models_ready: { type: boolean }
                  missing_models: { type: array, items: { type: string } }
                  engine_uuid: { type: string }
                  uptime_ms: { type: integer }

  /models:
    get:
      summary: List available models and download status
    post:
      summary: Start model download
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model: { type: string, enum: [whisper-base, openclip-vit-b-32, ssdlite320-mobilenet-v3] }

  /libraries:
    get:
      summary: List all libraries
    post:
      summary: Add a library (folder path)
    
  /libraries/{id}:
    get:
      summary: Get library details
    delete:
      summary: Remove library and all indexed data

  /libraries/{id}/scan:
    post:
      summary: Trigger rescan for new/changed/deleted files

  /videos:
    get:
      summary: List videos (with pagination, filtering)

  /videos/{id}:
    get:
      summary: Get video details + indexing status

  /search:
    post:
      summary: Multi-modal search
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [query]
              properties:
                query: { type: string }
                mode: { type: string, enum: [transcript, visual, both], default: both }
                labels: { type: array, items: { type: string } }
                library_id: { type: string }
                limit: { type: integer, default: 50 }
                offset: { type: integer, default: 0 }

  /jobs:
    get:
      summary: List active jobs

  /jobs/{id}:
    get:
      summary: Get job status
    delete:
      summary: Cancel job

  /settings:
    get:
      summary: Get all settings
    patch:
      summary: Update settings

  /export/captions/{video_id}:
    get:
      summary: Export captions as SRT or VTT
      parameters:
        - name: format
          in: query
          schema: { type: string, enum: [srt, vtt], default: srt }

  /shutdown:
    post:
      summary: Graceful shutdown (called by Tauri on quit)
```

### WebSocket Messages (JSON Schema)

```json
{
  "messages": {
    "subscribe": {
      "type": "object",
      "properties": {
        "type": { "const": "subscribe" },
        "topics": { "type": "array", "items": { "type": "string" } }
      }
    },
    "model_download_progress": {
      "type": "object",
      "properties": {
        "type": { "const": "model_download_progress" },
        "model": { "type": "string" },
        "progress": { "type": "number", "minimum": 0, "maximum": 1 },
        "bytes_downloaded": { "type": "integer" },
        "bytes_total": { "type": "integer" }
      }
    },
    "model_download_complete": {
      "type": "object",
      "properties": {
        "type": { "const": "model_download_complete" },
        "model": { "type": "string" }
      }
    },
    "scan_progress": {
      "type": "object",
      "properties": {
        "type": { "const": "scan_progress" },
        "library_id": { "type": "string" },
        "files_found": { "type": "integer" },
        "files_new": { "type": "integer" },
        "files_changed": { "type": "integer" },
        "files_deleted": { "type": "integer" }
      }
    },
    "job_progress": {
      "type": "object",
      "properties": {
        "type": { "const": "job_progress" },
        "job_id": { "type": "string" },
        "video_id": { "type": "string" },
        "stage": { "type": "string", "enum": ["extracting_audio", "transcribing", "extracting_frames", "embedding", "detecting"] },
        "progress": { "type": "number", "minimum": 0, "maximum": 1 },
        "message": { "type": "string" }
      }
    },
    "job_complete": {
      "type": "object",
      "properties": {
        "type": { "const": "job_complete" },
        "job_id": { "type": "string" },
        "video_id": { "type": "string" }
      }
    },
    "job_failed": {
      "type": "object",
      "properties": {
        "type": { "const": "job_failed" },
        "job_id": { "type": "string" },
        "video_id": { "type": "string" },
        "stage": { "type": "string" },
        "error_code": { "type": "string" },
        "error_message": { "type": "string" }
      }
    },
    "consistency_repair": {
      "type": "object",
      "properties": {
        "type": { "const": "consistency_repair" },
        "repairs": { "type": "array", "items": { "type": "object" } }
      }
    },
    "error": {
      "type": "object",
      "properties": {
        "type": { "const": "error" },
        "code": { "type": "string" },
        "message": { "type": "string" }
      }
    }
  }
}
```

### WebSocket Authentication

**V3 fixes V2's mismatch.** Both sides use the same mechanism:

```
Client → Server: Sec-WebSocket-Protocol: gaze-token.{base64_token}
Server → Client: Sec-WebSocket-Protocol: gaze-token.{base64_token}
```

If client cannot set `Sec-WebSocket-Protocol`, fallback to:

```
Client → Server: ?token={base64_token} (query string)
```

Server must accept **both**. Query string is logged as `?token=REDACTED`.

---

## Engine Lifecycle (Tauri + Python)

### Startup Sequence

```
1. Tauri app starts
2. Check for existing lockfile
   - If lockfile exists:
     a. Read port, token, engine_uuid
     b. Call GET /health with token
     c. If healthy AND uuid matches → reuse (skip to step 7)
     d. If unhealthy OR uuid mismatch:
        - Check if PID is alive
        - If alive + uuid mismatch → error (another engine?)
        - If dead → delete lockfile, continue
3. Find available port (48100-48199)
4. Generate 32-byte token
5. Write lockfile (port, token, uuid, pid=pending)
6. Spawn Python engine as sidecar
   - Pass: --port {port} --token {token} --parent-pid {tauri_pid}
   - Engine writes its PID to lockfile on startup
7. Poll GET /health until ready (with exponential backoff)
   - Max 30 seconds, then show error
8. Connect WebSocket
9. Subscribe to topics: [models, jobs, errors]
10. Check models_ready
    - If false → show model download UI
    - If true → show main UI
```

### Readiness Probe (Not a Timer)

V2's 15-second delay was a hack. V3 uses active polling:

```rust
// Tauri side (Rust)
async fn wait_for_engine_ready(port: u16, token: &str) -> Result<(), Error> {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{}/health", port);
    
    let mut delay = Duration::from_millis(100);
    let max_delay = Duration::from_secs(2);
    let deadline = Instant::now() + Duration::from_secs(30);
    
    while Instant::now() < deadline {
        match client.get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .timeout(Duration::from_secs(2))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {
                let health: HealthResponse = resp.json().await?;
                if health.status == "ready" {
                    return Ok(());
                }
            }
            _ => {}
        }
        
        tokio::time::sleep(delay).await;
        delay = (delay * 2).min(max_delay);
    }
    
    Err(Error::EngineStartupTimeout)
}
```

### Lockfile Management

**Path:**
- Windows: `%APPDATA%\Gaze\engine.lock`
- macOS: `~/Library/Application Support/Gaze/engine.lock`
- Linux: `~/.config/Gaze/engine.lock`

**Contents:**
```json
{
  "port": 48100,
  "token": "base64-encoded-32-bytes",
  "engine_uuid": "uuid-v4",
  "engine_pid": 12345,
  "parent_pid": 67890,
  "created_at_ms": 1705600000000
}
```

**Permissions:**
- Unix: `0600` (owner read/write only)
- Windows: ACL restricted to current user

**Staleness detection (on Tauri startup):**
```
Lockfile is stale if:
  - created_at_ms > 24 hours ago, AND
  - /health fails or times out, AND
  - PID is not alive
```

**Cleanup on Tauri quit:**
1. POST /shutdown to engine
2. Wait up to 3 seconds for graceful exit
3. If still running, kill PID
4. Delete lockfile

### Parent Death Detection (Engine Side)

```python
# Engine polls every 10 seconds
async def parent_monitor(parent_pid: int):
    consecutive_failures = 0
    
    while True:
        await asyncio.sleep(10)
        
        if not pid_exists(parent_pid):
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        
        if consecutive_failures >= 3:
            logger.warning("Parent process dead, shutting down")
            await graceful_shutdown()
            sys.exit(0)
```

---

## Indexing Pipeline

### Job State Machine

```
                    ┌─────────────┐
                    │   QUEUED    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ EXTRACTING  │
                    │   AUDIO     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │TRANSCRIBING │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ EXTRACTING  │
                    │   FRAMES    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  EMBEDDING  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  DETECTING  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    DONE     │
                    └─────────────┘

On error at any stage → FAILED (preserves stage info)
On cancel → CANCELLED
```

### Stage Details

**1. EXTRACTING_AUDIO**
- Input: Video file
- Output: WAV file (16kHz mono)
- Tool: FFmpeg
- Resumable: Yes (check if WAV exists and matches video mtime)

**2. TRANSCRIBING**
- Input: WAV file
- Output: Transcript segments in DB
- Tool: Whisper base
- Resumable: Yes (check if segments exist for video)

**3. EXTRACTING_FRAMES**
- Input: Video file
- Output: Thumbnail JPEGs on disk
- Tool: FFmpeg (1 frame per 2 seconds)
- Resumable: Yes (check frame count matches expected)

**4. EMBEDDING**
- Input: Thumbnail JPEGs
- Output: FAISS shard file
- Tool: OpenCLIP ViT-B-32
- Resumable: No (atomic: either shard exists or it doesn't)

**5. DETECTING**
- Input: Thumbnail JPEGs
- Output: Detection rows in DB
- Tool: SSDLite MobileNetV3
- Resumable: Yes (check if detections exist for video)

### Crash Recovery

On engine startup, run consistency check:

```python
async def reconcile_on_startup():
    # Find videos with incomplete indexing
    incomplete = db.query("""
        SELECT video_id, status, last_completed_stage 
        FROM videos 
        WHERE status NOT IN ('DONE', 'FAILED', 'CANCELLED')
    """)
    
    for video in incomplete:
        # Reset to last completed stage
        if video.last_completed_stage:
            next_stage = STAGE_ORDER[STAGE_ORDER.index(video.last_completed_stage) + 1]
            db.update_video_status(video.video_id, next_stage)
        else:
            db.update_video_status(video.video_id, 'QUEUED')
        
        # Re-queue for indexing
        job_queue.enqueue(video.video_id)
    
    # Clean up orphaned files
    cleanup_orphaned_thumbnails()
    cleanup_orphaned_faiss_shards()
    cleanup_temp_files()
```

---

## Search Architecture

### Multi-Modal Search (Same as V2, Clarified)

**Mode: TRANSCRIPT**
```sql
SELECT video_id, start_ms, end_ms, 
       highlight(transcript_fts, 3, '<mark>', '</mark>') as snippet,
       rank
FROM transcript_fts
WHERE transcript_fts MATCH ?
ORDER BY rank
LIMIT ?
```

Group into moments (±2s window), sort by BM25 rank.

**Mode: VISUAL**
```python
query_embedding = clip_model.encode_text(query)

results = []
for video in videos:
    shard_path = faiss_dir / f"{video.video_id}.faiss"
    if shard_path.exists():
        index = faiss.read_index(str(shard_path))
        distances, indices = index.search(query_embedding, k=20)
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0:
                frame = get_frame_by_index(video.video_id, idx)
                results.append((video.video_id, frame.timestamp_ms, 1 - dist))

# Group into moments (±3s window), sort by similarity
```

**Mode: BOTH**
```python
transcript_results = search_transcript(query)
visual_results = search_visual(query)

# Normalize scores to 0-1
transcript_scores = normalize(transcript_results)
visual_scores = normalize(visual_results)

# Merge
all_moments = set(transcript_scores.keys()) | set(visual_scores.keys())
merged = []

for moment in all_moments:
    t_score = transcript_scores.get(moment, 0)
    v_score = visual_scores.get(moment, 0)
    
    # Equal weight
    score = 0.5 * t_score + 0.5 * v_score
    
    # Detector boost: +0.05 per matching label (cap +0.15)
    matching_labels = get_matching_labels(moment, query)
    score += min(0.15, 0.05 * len(matching_labels))
    
    merged.append((moment, score))

return sorted(merged, key=lambda x: -x[1])
```

### Label Filtering

```python
if labels:
    # Filter moments to only those with matching detections
    moments = filter_by_labels(moments, labels)
```

---

## Database Schema (SQLite)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS libraries (
    library_id TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL UNIQUE,
    name TEXT,
    recursive INTEGER NOT NULL DEFAULT 1,
    created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mtime_ms INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,           -- NEW: content fingerprint
    duration_ms INTEGER,
    width INTEGER,
    height INTEGER,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    last_completed_stage TEXT,           -- NEW: for resumability
    progress REAL NOT NULL DEFAULT 0.0,
    error_code TEXT,
    error_message TEXT,
    language_code TEXT,
    indexed_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(library_id, path),
    FOREIGN KEY(library_id) REFERENCES libraries(library_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    video_id,
    start_ms,
    end_ms,
    text,
    tokenize="unicode61"
);

CREATE TABLE IF NOT EXISTS frames (
    frame_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    frame_index INTEGER NOT NULL,        -- NEW: position in FAISS shard
    timestamp_ms INTEGER NOT NULL,
    thumbnail_path TEXT NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS detections (
    detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox_x REAL,
    bbox_y REAL,
    bbox_w REAL,
    bbox_h REAL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY(frame_id) REFERENCES frames(frame_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    current_stage TEXT,
    progress REAL NOT NULL DEFAULT 0.0,
    message TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_videos_library ON videos(library_id);
CREATE INDEX IF NOT EXISTS idx_videos_fingerprint ON videos(fingerprint);
CREATE INDEX IF NOT EXISTS idx_segments_video ON transcript_segments(video_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_frames_video ON frames(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_detections_video ON detections(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_detections_label ON detections(label);
CREATE INDEX IF NOT EXISTS idx_jobs_video ON jobs(video_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
```

---

## Model Management

### Required Models

| Model | Purpose | Size | Source |
|-------|---------|------|--------|
| whisper-base | Speech recognition | ~140MB | OpenAI |
| openclip-vit-b-32 | Visual embeddings | ~350MB | HuggingFace |
| ssdlite320-mobilenet-v3 | Object detection | ~13MB | Torchvision (BSD) |

### Download Flow

```
1. App starts, checks /models endpoint
2. If any model missing → show download UI
3. User clicks "Download Models"
4. POST /models { model: "whisper-base" }
5. Engine downloads with progress events via WebSocket
6. Repeat for each missing model
7. When all complete → /health returns models_ready: true
8. Proceed to main UI
```

### Verification

Each model download includes SHA256 verification:

```python
MODELS = {
    "whisper-base": {
        "url": "https://openaipublic.blob.core.windows.net/main/whisper/models/whisper-base.pt",
        "sha256": "...",
        "size_bytes": 147000000
    },
    "openclip-vit-b-32": {
        "url": "https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K/...",
        "sha256": "...",
        "size_bytes": 350000000
    },
    "ssdlite320-mobilenet-v3": {
        "url": "https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth",
        "sha256": "...",
        "size_bytes": 13409236
    }
}
```

---

## Security

Carried forward from V2's SECURITY.md with clarifications:

### Network Policy
- Engine binds to `127.0.0.1` only
- Only outbound connections: model downloads (explicit user action)
- No analytics, no update checks, no telemetry

### Authentication
- 32-byte random token generated on each engine start
- All HTTP requests require `Authorization: Bearer {token}`
- WebSocket requires `Sec-WebSocket-Protocol: gaze-token.{token}` or query string fallback
- Token stored in lockfile with user-only permissions

### Logging
- Tokens redacted from all logs
- Paths can be logged (no PII in paths)
- Support mode (opt-in) can include full paths

### Model Provenance
- All downloads verified with SHA256
- Checksum mismatch = download failed, user notified

---

## Development Milestones

### Phase 1: Foundation (Weeks 1-2)

**Week 1: Scaffolding**
- [ ] Initialize Tauri project with React
- [ ] Initialize Python engine with FastAPI
- [ ] Define OpenAPI spec (core endpoints)
- [ ] Generate TypeScript client from spec
- [ ] Basic lockfile management in Tauri (Rust)
- [ ] Basic engine lifecycle (spawn, health check)
- [ ] "Hello World" end-to-end: Tauri → Engine → Response → UI

**Week 2: Packaging**
- [ ] PyInstaller build for engine (all platforms)
- [ ] Tauri sidecar configuration
- [ ] GitHub Actions: build installers (unsigned)
- [ ] Test on clean Windows VM
- [ ] Test on clean macOS VM
- [ ] Test on clean Ubuntu VM

**Exit criteria:** Installer runs on clean machine, shows "Engine connected" in UI.

### Phase 2: Core Pipeline (Weeks 3-4)

**Week 3: Models + Scanning**
- [ ] Model download endpoints
- [ ] Model download UI (progress bar)
- [ ] SHA256 verification
- [ ] Library add endpoint
- [ ] File scanner with fingerprinting
- [ ] Scan progress via WebSocket

**Week 4: Indexing**
- [ ] Job state machine implementation
- [ ] FFmpeg audio extraction
- [ ] Whisper transcription
- [ ] Frame extraction
- [ ] OpenCLIP embedding
- [ ] FAISS shard writing
- [ ] SSDLite detection
- [ ] Job progress via WebSocket

**Exit criteria:** Add folder → Videos index → Jobs complete.

### Phase 3: Search + Playback (Weeks 5-6)

**Week 5: Search**
- [ ] Transcript FTS search
- [ ] Visual FAISS search
- [ ] Merged search with detector boost
- [ ] Search results API
- [ ] Search UI (input + results list)

**Week 6: Playback**
- [ ] Video player component
- [ ] Timestamp seeking
- [ ] Transcript panel
- [ ] Click result → Play at timestamp
- [ ] Caption export (SRT/VTT)

**Exit criteria:** Search "dog" → Results with thumbnails → Click → Video plays at timestamp.

### Phase 4: Polish + Distribution (Weeks 7-8)

**Week 7: Reliability**
- [ ] Crash recovery / consistency check
- [ ] Stale lockfile cleanup
- [ ] Error handling + user messages
- [ ] Rescan for deleted/changed files
- [ ] Settings UI (disk limits, model sources)

**Week 8: Distribution**
- [ ] Code signing (Windows)
- [ ] Notarization (macOS)
- [ ] Auto-update mechanism
- [ ] Release workflow (tag → build → publish)
- [ ] Beta testing (3-5 users on real machines)

**Exit criteria:** Signed installers available for download. Beta users can install and use without developer assistance.

---

## Success Metrics

### Functional
- [ ] Index 100-video library without crashes
- [ ] Search returns relevant results in <500ms
- [ ] Engine restarts cleanly after force-quit
- [ ] Clean-machine install works first try

### Quality
- [ ] No "Engine not connected" when engine is running
- [ ] All progress events arrive in UI
- [ ] Error messages are actionable (not "Unknown error")
- [ ] Zero debugging sessions for "it worked on my machine"

### Distribution
- [ ] Windows installer: signed, no SmartScreen warning
- [ ] macOS installer: notarized, no Gatekeeper block
- [ ] Linux AppImage: runs on Ubuntu 22.04+

---

## Open Questions

1. **Auto-update mechanism:** Tauri supports it natively. Enable from day one, or add in V3.1?

2. **Crash reporting:** Optional Sentry integration? Must be opt-in with clear privacy disclosure.

3. **Thumbnail storage:** On disk (V2 approach) or in SQLite blobs (simpler but larger DB)?

4. **FAISS merge:** Per-video shards are simple but slow for large libraries. When to implement library-level merge?

5. **GPU acceleration:** Whisper and CLIP can use GPU if available. Detect and enable, or CPU-only for V3.0?

---

## Appendix: V2 → V3 Migration

If existing V2 users need to migrate data:

1. Export libraries and settings from V2 SQLite
2. On V3 first run, detect V2 data directory
3. Offer to import libraries (re-scan, no re-index if fingerprints match)
4. V3 will re-compute fingerprints and verify existing indexes

This is low priority for V3.0 (no V2 users in the wild yet).

---

*End of V3 Architecture Document*
