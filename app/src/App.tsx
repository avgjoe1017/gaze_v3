import { useEffect, useState } from "react";
import { useEngine } from "./hooks/useEngine";
import { useWebSocket, useModelDownloadProgress, useScanProgress, useJobProgress } from "./hooks/useWebSocket";
import { ModelDownload } from "./components/ModelDownload";
import { MainView } from "./components/MainView";
import { LogViewer } from "./components/LogViewer";
import { Analytics } from "./components/Analytics";
import { Faces } from "./components/Faces";
import { SettingsView } from "./components/SettingsView";
import { PrivacyView } from "./components/PrivacyView";
import { apiRequest } from "./lib/apiClient";

// Icons
const EyeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const SunIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <line x1="12" y1="2" x2="12" y2="5" />
    <line x1="12" y1="19" x2="12" y2="22" />
    <line x1="2" y1="12" x2="5" y2="12" />
    <line x1="19" y1="12" x2="22" y2="12" />
    <line x1="4.5" y1="4.5" x2="6.7" y2="6.7" />
    <line x1="17.3" y1="17.3" x2="19.5" y2="19.5" />
    <line x1="4.5" y1="19.5" x2="6.7" y2="17.3" />
    <line x1="17.3" y1="6.7" x2="19.5" y2="4.5" />
  </svg>
);

const MoonIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.6A9 9 0 1 1 11.4 3a7 7 0 0 0 9.6 9.6z" />
  </svg>
);

interface SettingsData {
  max_concurrent_jobs: number;
  thumbnail_quality: number;
  frame_interval_seconds: number;
  faiss_cache_max: number;
  indexing_preset: string;
  transcription_model: string;
  transcription_language: string | null;
  transcription_backend: string;
  transcription_vad_enabled: boolean;
  transcription_min_silence_ms: number;
  transcription_silence_threshold_db: number;
  transcription_chunk_seconds: number | null;
  offline_mode: boolean;
  face_recognition_enabled: boolean;
}

function App() {
  const { status, health, error, port, startEngine } = useEngine();
  const { connected: wsConnected, addHandler } = useWebSocket({ port, enabled: status === "connected" });
  const modelDownloads = useModelDownloadProgress(addHandler);
  const scanProgress = useScanProgress(addHandler);
  const jobProgress = useJobProgress(addHandler);
  const [showLogs, setShowLogs] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    const stored = window.localStorage.getItem("gaze-theme");
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    const prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("gaze-theme", theme);
  }, [theme]);

  const fetchSettings = async () => {
    if (status !== "connected") return;
    setSettingsLoading(true);
    try {
      const data = await apiRequest<SettingsData>("/settings");
      setSettings(data);
    } catch (err) {
      console.error("[Settings] Failed to load:", err);
      setSettings(null);
    } finally {
      setSettingsLoading(false);
    }
  };

  useEffect(() => {
    if (status === "connected") {
      fetchSettings();
    } else {
      setSettings(null);
    }
  }, [status]);

  const updateSettings = async (update: Partial<SettingsData>) => {
    const data = await apiRequest<SettingsData>("/settings", {
      method: "PATCH",
      body: JSON.stringify(update),
    });
    setSettings(data);
  };

  const faceRecognitionEnabled = settings?.face_recognition_enabled ?? false;
  const offlineMode = settings?.offline_mode ?? false;

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <div className="logo-mark">
            <EyeIcon />
          </div>
          <span className="logo-text">SafeKeeps</span>
          <span className="logo-version">Vault</span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {status === "connected" && (
            <>
              <button
                onClick={() => {
                  if (!faceRecognitionEnabled) {
                    setShowSettings(true);
                    setShowFaces(false);
                    setShowAnalytics(false);
                    setShowLogs(false);
                    return;
                  }
                  setShowFaces(!showFaces);
                  setShowAnalytics(false);
                  setShowLogs(false);
                  setShowSettings(false);
                  setShowPrivacy(false);
                }}
                className={`btn-pill ${showFaces ? "active" : ""} ${faceRecognitionEnabled ? "" : "disabled"}`}
                title={faceRecognitionEnabled ? "Toggle face recognition" : "Enable face recognition in Settings"}
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="3" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a3 3 0 0 1 0 5.74" />
                </svg>
                Faces
              </button>
              <button
                onClick={() => {
                  setShowAnalytics(!showAnalytics);
                  setShowLogs(false);
                  setShowFaces(false);
                  setShowSettings(false);
                  setShowPrivacy(false);
                }}
                className={`btn-pill ${showAnalytics ? "active" : ""}`}
                title="Toggle analytics dashboard"
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="20" x2="12" y2="10" />
                  <line x1="18" y1="20" x2="18" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="16" />
                </svg>
                Analytics
              </button>
              <button
                onClick={() => {
                  setShowLogs(!showLogs);
                  setShowAnalytics(false);
                  setShowFaces(false);
                  setShowSettings(false);
                  setShowPrivacy(false);
                }}
                className={`btn-pill ${showLogs ? "active" : ""}`}
                title="Toggle logs viewer"
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="4 17 10 11 4 5" />
                  <line x1="12" y1="19" x2="20" y2="19" />
                </svg>
                Logs
              </button>
              <button
                onClick={() => {
                  setShowSettings(!showSettings);
                  setShowLogs(false);
                  setShowAnalytics(false);
                  setShowFaces(false);
                  setShowPrivacy(false);
                }}
                className={`btn-pill ${showSettings ? "active" : ""}`}
                title="Open settings"
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.7 1.7 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.82-.33 1.7 1.7 0 0 0-1 1.54V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.54 1.7 1.7 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.54-1H3a2 2 0 1 1 0-4h.06a1.7 1.7 0 0 0 1.54-1 1.7 1.7 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 8 4.6a1.7 1.7 0 0 0 1-1.54V3a2 2 0 1 1 4 0v.06a1.7 1.7 0 0 0 1 1.54 1.7 1.7 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.33 1.82 1.7 1.7 0 0 0 1.54 1H21a2 2 0 1 1 0 4h-.06a1.7 1.7 0 0 0-1.54 1z" />
                </svg>
                Settings
              </button>
              <button
                onClick={() => {
                  setShowPrivacy(!showPrivacy);
                  setShowLogs(false);
                  setShowAnalytics(false);
                  setShowFaces(false);
                  setShowSettings(false);
                }}
                className={`btn-pill ${showPrivacy ? "active" : ""}`}
                title="Privacy and networking status"
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z" />
                </svg>
                Privacy
              </button>
            </>
          )}
          <button
            className="theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            <span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
          <StatusBadge status={status} wsConnected={wsConnected} />
        </div>
      </header>

      <main className="main">
        {status === "disconnected" && (
          <div className="center-panel">
            <div className="empty-state-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M18.364 5.636a9 9 0 0 1 0 12.728M5.636 18.364a9 9 0 0 1 0-12.728" strokeLinecap="round" />
                <path d="M15.536 8.464a5 5 0 0 1 0 7.072M8.464 15.536a5 5 0 0 1 0-7.072" strokeLinecap="round" />
                <circle cx="12" cy="12" r="1" fill="currentColor" />
              </svg>
            </div>
            <h2>Engine Disconnected</h2>
            <p>
              {error
                ? error
                : "The SafeKeeps Vault engine is not running. Start it to begin searching your photos and videos."}
            </p>
            <button className="btn btn-primary" onClick={startEngine} style={{ marginTop: 24 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none" />
              </svg>
              Start Engine
            </button>
          </div>
        )}

        {status === "starting" && (
          <div className="center-panel">
            <div className="spinner spinner-large" />
            <h2>Starting Engine</h2>
            <p>Initializing the SafeKeeps Vault engine. This may take a moment...</p>
          </div>
        )}

        {status === "connected" && health && health.status === "error" && health.dependencies && !showPrivacy && (
          !health.dependencies.ffmpeg_available || !health.dependencies.ffprobe_available
        ) && (
          <div className="center-panel">
            <div className="empty-state-icon" style={{ color: "var(--status-error)" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h2>FFmpeg Required</h2>
            <p style={{ maxWidth: 480, lineHeight: 1.6 }}>
              SafeKeeps Vault requires FFmpeg to process video files. FFmpeg is a free, open-source tool
              for handling multimedia content.
            </p>

            <div style={{
              background: "var(--bg-secondary)",
              borderRadius: 8,
              padding: 20,
              marginTop: 24,
              textAlign: "left",
              maxWidth: 520
            }}>
              <h3 style={{ fontSize: 14, marginBottom: 12, color: "var(--text-primary)" }}>
                Installation Instructions
              </h3>

              <div style={{ marginBottom: 16 }}>
                <strong style={{ fontSize: 13 }}>Windows:</strong>
                <code style={{
                  display: "block",
                  background: "var(--bg-primary)",
                  padding: "8px 12px",
                  borderRadius: 4,
                  marginTop: 6,
                  fontSize: 12
                }}>
                  choco install ffmpeg
                </code>
                <span style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4, display: "block" }}>
                  Or download from <a href="https://ffmpeg.org/download.html" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>ffmpeg.org</a> and add to PATH
                </span>
              </div>

              <div style={{ marginBottom: 16 }}>
                <strong style={{ fontSize: 13 }}>macOS:</strong>
                <code style={{
                  display: "block",
                  background: "var(--bg-primary)",
                  padding: "8px 12px",
                  borderRadius: 4,
                  marginTop: 6,
                  fontSize: 12
                }}>
                  brew install ffmpeg
                </code>
              </div>

              <div>
                <strong style={{ fontSize: 13 }}>Linux (Ubuntu/Debian):</strong>
                <code style={{
                  display: "block",
                  background: "var(--bg-primary)",
                  padding: "8px 12px",
                  borderRadius: 4,
                  marginTop: 6,
                  fontSize: 12
                }}>
                  sudo apt install ffmpeg
                </code>
              </div>
            </div>

            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 20 }}>
              After installing FFmpeg, restart SafeKeeps Vault to continue.
            </p>

            <button
              className="btn btn-primary"
              onClick={() => window.location.reload()}
              style={{ marginTop: 16 }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Check Again
            </button>
          </div>
        )}

        {status === "connected" && health && !health.models_ready && health.status !== "error" && !showSettings && !showPrivacy && (
          <div className="center-panel">
            <h2>Setup Required</h2>
            <p>
              Before searching your photos and videos, download the required ML models.
              These run locally on your machine for complete privacy.
            </p>
            <ModelDownload
              missingModels={health.missing_models}
              wsDownloads={modelDownloads}
              offlineMode={offlineMode}
            />
          </div>
        )}

        {status === "connected" && showSettings && (
          <SettingsView
            settings={settings}
            loading={settingsLoading}
            onRefresh={fetchSettings}
            onUpdate={updateSettings}
          />
        )}

        {status === "connected" && showPrivacy && (
          <PrivacyView
            offlineMode={offlineMode}
            onUpdate={(update) => updateSettings(update)}
          />
        )}

        {status === "connected" && health?.models_ready && !showSettings && !showPrivacy && (
          <>
            {showLogs ? (
              <LogViewer port={port!} />
            ) : showAnalytics ? (
              <Analytics />
            ) : showFaces ? (
              <Faces />
            ) : (
              <MainView
                scanProgress={scanProgress}
                jobProgress={jobProgress}
                faceRecognitionEnabled={faceRecognitionEnabled}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function StatusBadge({
  status,
  wsConnected
}: {
  status: "connected" | "disconnected" | "starting";
  wsConnected: boolean;
}) {
  const labels = {
    connected: "Ready",
    disconnected: "Offline",
    starting: "Starting",
  };

  return (
    <div className="status-badges">
      <div className={`status-badge ${status}`} title={status === "connected" ? "Engine running locally" : undefined}>
        <span className="status-dot" />
        {labels[status]}
      </div>
      {status === "connected" && (
        <div
          className={`status-badge ${wsConnected ? "ws-connected" : "ws-disconnected"}`}
          title={wsConnected ? "Live local updates" : "Local link reconnecting"}
        >
          <span className="status-dot" />
          {wsConnected ? "Live updates" : "Reconnecting"}
        </div>
      )}
    </div>
  );
}

export default App;
