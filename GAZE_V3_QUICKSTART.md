# Gaze V3 Quick Start Checklist

**Goal:** Get to "installer runs on clean machine" in 2 weeks.

---

## Day 1: Project Setup

### Tauri App
```bash
# Install Tauri CLI
cargo install tauri-cli

# Create new Tauri + React project
npm create tauri-app@latest gaze-v3 -- --template react-ts

cd gaze-v3
npm install

# Verify it runs
npm run tauri dev
```

### Python Engine
```bash
mkdir engine
cd engine

# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[project]
name = "gaze-engine"
version = "3.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "websockets>=12.0",
    "pydantic>=2.5.0",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
ml = [
    "openai-whisper>=20231117",
    "open-clip-torch>=2.24.0",
    "torch>=2.0.0",
    "torchvision>=0.16.0",
    "faiss-cpu>=1.7.4",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
EOF

# Create minimal structure
mkdir -p src/engine
touch src/engine/__init__.py

# Install (without ML deps for now, faster iteration)
pip install -e .
```

### Verify Both Run
```bash
# Terminal 1: Engine
cd engine
python -c "from fastapi import FastAPI; print('FastAPI OK')"

# Terminal 2: Tauri
cd gaze-v3
npm run tauri dev
```

---

## Day 2: OpenAPI Contract

### Create Contract File
```bash
mkdir contracts
cat > contracts/openapi.yaml << 'EOF'
openapi: 3.1.0
info:
  title: Gaze Engine API
  version: 3.0.0
servers:
  - url: http://127.0.0.1:{port}
    variables:
      port:
        default: "48100"

paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: Engine health
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/HealthResponse"

  /shutdown:
    post:
      operationId: shutdown
      responses:
        "200":
          description: Shutdown initiated

components:
  schemas:
    HealthResponse:
      type: object
      required:
        - status
        - engine_uuid
      properties:
        status:
          type: string
          enum: [starting, ready, error]
        models_ready:
          type: boolean
        engine_uuid:
          type: string
        uptime_ms:
          type: integer
EOF
```

### Generate TypeScript Client
```bash
# Install generator
npm install -g @openapitools/openapi-generator-cli

# Generate client
openapi-generator-cli generate \
  -i contracts/openapi.yaml \
  -g typescript-fetch \
  -o gaze-v3/src/api/generated \
  --additional-properties=supportsES6=true,typescriptThreePlus=true
```

---

## Day 3: Minimal Engine

### Create main.py
```python
# engine/src/engine/main.py
import argparse
import asyncio
import uuid
from datetime import datetime
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Gaze Engine", version="3.0.0")

# State
ENGINE_UUID = str(uuid.uuid4())
START_TIME = datetime.now()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {
        "status": "ready",
        "models_ready": False,  # TODO: check actual models
        "engine_uuid": ENGINE_UUID,
        "uptime_ms": int((datetime.now() - START_TIME).total_seconds() * 1000)
    }

@app.post("/shutdown")
async def shutdown():
    # Graceful shutdown
    asyncio.get_event_loop().call_later(0.5, lambda: exit(0))
    return {"status": "shutting_down"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=48100)
    parser.add_argument("--token", type=str, default="dev-token")
    args = parser.parse_args()
    
    uvicorn.run(app, host="127.0.0.1", port=args.port)

if __name__ == "__main__":
    main()
```

### Test It
```bash
# Start engine
python -m engine.main --port 48100

# In another terminal
curl http://127.0.0.1:48100/health
# Should return: {"status":"ready","models_ready":false,"engine_uuid":"...","uptime_ms":...}
```

---

## Day 4-5: Tauri Engine Lifecycle

### Configure Sidecar (tauri.conf.json)
```json
{
  "bundle": {
    "externalBin": [
      "binaries/gaze-engine"
    ]
  }
}
```

### Rust Engine Manager
```rust
// src-tauri/src/engine.rs
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::State;

pub struct EngineState {
    process: Mutex<Option<Child>>,
    port: Mutex<u16>,
    token: Mutex<String>,
}

impl EngineState {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
            port: Mutex::new(48100),
            token: Mutex::new(String::new()),
        }
    }
}

#[tauri::command]
pub async fn start_engine(state: State<'_, EngineState>) -> Result<u16, String> {
    let port = 48100; // TODO: find available port
    let token = uuid::Uuid::new_v4().to_string();
    
    let child = Command::new("python")
        .args(["-m", "engine.main", "--port", &port.to_string(), "--token", &token])
        .spawn()
        .map_err(|e| e.to_string())?;
    
    *state.process.lock().unwrap() = Some(child);
    *state.port.lock().unwrap() = port;
    *state.token.lock().unwrap() = token;
    
    // TODO: wait for health check
    
    Ok(port)
}

#[tauri::command]
pub async fn stop_engine(state: State<'_, EngineState>) -> Result<(), String> {
    if let Some(mut child) = state.process.lock().unwrap().take() {
        child.kill().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn get_engine_port(state: State<'_, EngineState>) -> u16 {
    *state.port.lock().unwrap()
}
```

### Register Commands (main.rs)
```rust
mod engine;

fn main() {
    tauri::Builder::default()
        .manage(engine::EngineState::new())
        .invoke_handler(tauri::generate_handler![
            engine::start_engine,
            engine::stop_engine,
            engine::get_engine_port,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

---

## Day 6-7: Connect UI to Engine

### React Hook
```tsx
// src/hooks/useEngine.ts
import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface EngineStatus {
  connected: boolean;
  port: number | null;
  health: {
    status: string;
    models_ready: boolean;
  } | null;
}

export function useEngine() {
  const [status, setStatus] = useState<EngineStatus>({
    connected: false,
    port: null,
    health: null,
  });

  useEffect(() => {
    let mounted = true;

    async function connect() {
      try {
        const port = await invoke<number>('start_engine');
        
        // Poll health
        const checkHealth = async () => {
          try {
            const res = await fetch(`http://127.0.0.1:${port}/health`);
            const health = await res.json();
            if (mounted) {
              setStatus({ connected: true, port, health });
            }
          } catch {
            if (mounted) {
              setStatus(s => ({ ...s, connected: false }));
            }
          }
        };

        await checkHealth();
        const interval = setInterval(checkHealth, 5000);
        
        return () => clearInterval(interval);
      } catch (err) {
        console.error('Failed to start engine:', err);
      }
    }

    connect();

    return () => {
      mounted = false;
      invoke('stop_engine').catch(console.error);
    };
  }, []);

  return status;
}
```

### App Component
```tsx
// src/App.tsx
import { useEngine } from './hooks/useEngine';

function App() {
  const engine = useEngine();

  return (
    <div className="app">
      <header>
        <h1>Gaze V3</h1>
        <div className={`status ${engine.connected ? 'connected' : 'disconnected'}`}>
          {engine.connected ? '🟢 Engine Running' : '🔴 Engine Disconnected'}
        </div>
      </header>
      
      <main>
        {!engine.connected && (
          <p>Starting engine...</p>
        )}
        
        {engine.connected && !engine.health?.models_ready && (
          <div>
            <h2>Download Models</h2>
            <p>Required models are not installed.</p>
            <button>Download All Models</button>
          </div>
        )}
        
        {engine.connected && engine.health?.models_ready && (
          <div>
            <h2>Ready to Search</h2>
            <p>Add a folder to get started.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
```

---

## Week 2: Packaging

### PyInstaller Spec
```bash
# Create spec file
cat > engine/gaze-engine.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['src/engine/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['uvicorn.logging', 'uvicorn.protocols.http'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gaze-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
EOF

# Build
cd engine
pip install pyinstaller
pyinstaller gaze-engine.spec
# Output: dist/gaze-engine (or gaze-engine.exe on Windows)
```

### Copy to Tauri
```bash
# macOS/Linux
mkdir -p gaze-v3/src-tauri/binaries
cp engine/dist/gaze-engine gaze-v3/src-tauri/binaries/gaze-engine-x86_64-apple-darwin

# Windows
cp engine/dist/gaze-engine.exe gaze-v3/src-tauri/binaries/gaze-engine-x86_64-pc-windows-msvc.exe
```

### Build Tauri App
```bash
cd gaze-v3
npm run tauri build
# Output: src-tauri/target/release/bundle/
```

### Test on Clean Machine
1. Copy installer to VM with no dev tools
2. Run installer
3. Launch app
4. Verify "Engine Running" shows in UI

---

## End of Week 2 Checklist

- [ ] `npm run tauri dev` shows UI
- [ ] UI shows "Engine Running" status
- [ ] `/health` returns valid JSON
- [ ] PyInstaller builds without errors
- [ ] Tauri bundles with sidecar
- [ ] Installer runs on clean Windows VM
- [ ] Installer runs on clean macOS VM
- [ ] Installer runs on clean Linux VM

If all boxes checked, you're ahead of V2's progress after months of work.

---

## Common Issues

### "Engine not found"
- Check sidecar path in `tauri.conf.json`
- Verify binary name matches platform pattern

### "Port already in use"
- Implement port scanning (48100-48199)
- Check for orphan processes

### "Module not found" in PyInstaller
- Add to `hiddenimports` in spec file
- Common: uvicorn.logging, anyio._backends._asyncio

### Tauri command not found
- Ensure `invoke_handler` includes the command
- Check State type matches

---

## Next: Phase 2

After Week 2, move to:
1. Model download endpoints
2. Library scanning
3. Indexing pipeline

See GAZE_V3_ARCHITECTURE.md for full roadmap.
