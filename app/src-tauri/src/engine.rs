use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, State};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Wrapper for different process types (std::process vs tauri sidecar)
pub enum EngineProcess {
    /// Standard library Child process (used in dev mode with Python)
    StdProcess(Child),
    /// Tauri sidecar CommandChild (used in release mode)
    SidecarProcess(CommandChild),
}

impl EngineProcess {
    /// Kill the underlying process (consumes self since CommandChild::kill takes ownership)
    pub fn kill(self) -> std::io::Result<()> {
        match self {
            EngineProcess::StdProcess(mut child) => child.kill(),
            EngineProcess::SidecarProcess(child) => {
                child.kill().map_err(|e| {
                    std::io::Error::new(std::io::ErrorKind::Other, e.to_string())
                })
            }
        }
    }
}

/// Engine state managed by Tauri
pub struct EngineState {
    process: Mutex<Option<EngineProcess>>,
    port: Mutex<u16>,
    token: Mutex<String>,
    status: Mutex<EngineStatus>,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
pub enum EngineStatus {
    Stopped,
    Starting,
    Running,
    Error,
}

#[derive(Serialize)]
pub struct EngineInfo {
    pub port: u16,
    pub status: EngineStatus,
}

impl EngineState {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
            port: Mutex::new(48100),
            token: Mutex::new(String::new()),
            status: Mutex::new(EngineStatus::Stopped),
        }
    }
}

/// Find an available port in the range 48100-48199
fn find_available_port() -> Result<u16, String> {
    for port in 48100..48200 {
        if std::net::TcpListener::bind(format!("127.0.0.1:{}", port)).is_ok() {
            return Ok(port);
        }
    }
    Err("No available port in range 48100-48199".to_string())
}

/// Generate a secure random token
fn generate_token() -> String {
    let mut rng = rand::thread_rng();
    let bytes: [u8; 32] = rng.gen();
    URL_SAFE_NO_PAD.encode(bytes)
}

/// Get the path to the Python engine module (for development mode)
fn get_engine_module_path() -> Result<String, String> {
    let current_dir = std::env::current_dir().map_err(|e| e.to_string())?;

    // Try multiple path strategies:
    // 1. If in app/src-tauri, go up twice to root, then engine/src
    // 2. If in app, go up once to root, then engine/src
    // 3. If already at root, use engine/src directly
    let engine_paths = vec![
        current_dir
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.join("engine").join("src")),
        current_dir.parent().map(|p| p.join("engine").join("src")),
        Some(current_dir.join("engine").join("src")),
    ];

    for path_opt in engine_paths {
        if let Some(path) = path_opt {
            if path.exists() {
                return Ok(path.to_string_lossy().to_string());
            }
        }
    }

    Err(format!(
        "Engine path not found. Current dir: {}",
        current_dir.display()
    ))
}

/// Spawn engine using Python (development mode or fallback)
fn spawn_python_engine(
    port: u16,
    token: &str,
    parent_pid: &str,
    log_level: &str,
) -> Result<EngineProcess, String> {
    let engine_path = get_engine_module_path()?;

    let child = Command::new("python")
        .args([
            "-m",
            "engine.main",
            "--port",
            &port.to_string(),
            "--token",
            token,
            "--parent-pid",
            parent_pid,
            "--log-level",
            log_level,
        ])
        .env("PYTHONPATH", &engine_path)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("Failed to spawn Python engine: {}", e))?;

    Ok(EngineProcess::StdProcess(child))
}

/// Spawn engine using bundled sidecar binary (release mode)
fn spawn_sidecar_engine(
    app: &AppHandle,
    port: u16,
    token: &str,
    parent_pid: &str,
    log_level: &str,
) -> Result<EngineProcess, String> {
    use tauri_plugin_shell::process::CommandEvent;

    let sidecar = app
        .shell()
        .sidecar("gaze-engine")
        .map_err(|e| format!("Failed to get sidecar: {}", e))?
        .args([
            "--port",
            &port.to_string(),
            "--token",
            token,
            "--parent-pid",
            parent_pid,
            "--log-level",
            log_level,
        ]);

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    // Spawn a task to handle output (relay to console)
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line = String::from_utf8_lossy(&line);
                    print!("{}", line);
                }
                CommandEvent::Stderr(line) => {
                    let line = String::from_utf8_lossy(&line);
                    eprint!("{}", line);
                }
                CommandEvent::Error(err) => {
                    eprintln!("Engine error: {}", err);
                }
                CommandEvent::Terminated(status) => {
                    println!("Engine terminated with status: {:?}", status);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(EngineProcess::SidecarProcess(child))
}

#[tauri::command]
pub async fn start_engine(
    app: AppHandle,
    state: State<'_, EngineState>,
) -> Result<u16, String> {
    // Check if already running or starting
    {
        let status = state.status.lock().unwrap();
        if *status == EngineStatus::Running || *status == EngineStatus::Starting {
            let port = *state.port.lock().unwrap();
            return Ok(port);
        }
    }

    // Update status to starting
    *state.status.lock().unwrap() = EngineStatus::Starting;

    // Find available port and generate token
    let port = find_available_port()?;
    let token = generate_token();

    // In development, use DEBUG log level; in production use INFO
    let log_level = if cfg!(debug_assertions) {
        "DEBUG"
    } else {
        "INFO"
    };

    let parent_pid = std::process::id().to_string();

    // In release builds, use the bundled sidecar binary
    // In debug builds, use Python directly for easier development
    let process_result = if cfg!(debug_assertions) {
        // Development mode: always use Python
        spawn_python_engine(port, &token, &parent_pid, log_level)
    } else {
        // Release mode: try sidecar first, fall back to Python
        match spawn_sidecar_engine(&app, port, &token, &parent_pid, log_level) {
            Ok(process) => Ok(process),
            Err(sidecar_err) => {
                eprintln!(
                    "Sidecar not found, falling back to Python: {}",
                    sidecar_err
                );
                spawn_python_engine(port, &token, &parent_pid, log_level)
            }
        }
    };

    let process = match process_result {
        Ok(process) => process,
        Err(err) => {
            *state.status.lock().unwrap() = EngineStatus::Error;
            *state.process.lock().unwrap() = None;
            *state.token.lock().unwrap() = String::new();
            return Err(err);
        }
    };

    // Store state
    *state.process.lock().unwrap() = Some(process);
    *state.port.lock().unwrap() = port;
    *state.token.lock().unwrap() = token;
    *state.status.lock().unwrap() = EngineStatus::Running;

    Ok(port)
}

#[tauri::command]
pub async fn stop_engine(state: State<'_, EngineState>) -> Result<(), String> {
    let port = *state.port.lock().unwrap();
    let token = state.token.lock().unwrap().clone();

    // Try graceful shutdown first via HTTP
    let client = reqwest::Client::new();
    let mut request = client
        .post(format!("http://127.0.0.1:{}/shutdown", port))
        .timeout(Duration::from_secs(3));
    if !token.is_empty() {
        request = request.bearer_auth(token);
    }
    let _ = request.send().await;

    // Wait a bit for graceful shutdown
    tokio::time::sleep(Duration::from_millis(500)).await;

    // Kill process if still running
    if let Some(process) = state.process.lock().unwrap().take() {
        let _ = process.kill();
    }

    *state.status.lock().unwrap() = EngineStatus::Stopped;
    *state.token.lock().unwrap() = String::new();

    Ok(())
}

#[tauri::command]
pub fn get_engine_port(state: State<'_, EngineState>) -> u16 {
    *state.port.lock().unwrap()
}

#[tauri::command]
pub fn get_engine_status(state: State<'_, EngineState>) -> EngineInfo {
    EngineInfo {
        port: *state.port.lock().unwrap(),
        status: *state.status.lock().unwrap(),
    }
}

#[tauri::command]
pub fn get_engine_token(state: State<'_, EngineState>) -> String {
    state.token.lock().unwrap().clone()
}
