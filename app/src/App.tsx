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

const MoreIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="1" />
    <circle cx="12" cy="5" r="1" />
    <circle cx="12" cy="19" r="1" />
  </svg>
);

interface SettingsData {
  max_concurrent_jobs: number;
  thumbnail_quality: number;
  frame_interval_seconds: number;
  faiss_cache_max: number;
  indexing_preset: string;
  prioritize_recent_media: boolean;
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

interface IndexingStatus {
  paused: boolean;
  active_jobs: number;
  queued_videos: number;
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
  const [indexingStatus, setIndexingStatus] = useState<IndexingStatus | null>(null);
  const [showHealthDetails, setShowHealthDetails] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
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

  // Close "More" dropdown when clicking outside
  useEffect(() => {
    if (!showMoreMenu) return;
    
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".more-menu-container")) {
        setShowMoreMenu(false);
      }
    };
    
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showMoreMenu]);

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

  const fetchIndexingStatus = async () => {
    if (status !== "connected") return;
    try {
      const data = await apiRequest<IndexingStatus>("/jobs/status");
      setIndexingStatus(data);
    } catch (err) {
      console.error("[Indexing] Failed to load status:", err);
    }
  };

  useEffect(() => {
    if (status === "connected") {
      fetchSettings();
      fetchIndexingStatus();
      const interval = setInterval(fetchIndexingStatus, 3000);
      return () => clearInterval(interval);
    } else {
      setSettings(null);
      setIndexingStatus(null);
    }
  }, [status]);

  const handlePauseResumeIndexing = async () => {
    if (!indexingStatus) return;
    try {
      if (indexingStatus.paused) {
        await apiRequest("/jobs/resume", { method: "POST" });
      } else {
        await apiRequest("/jobs/pause", { method: "POST" });
      }
      await fetchIndexingStatus();
    } catch (err) {
      console.error("Failed to pause/resume indexing:", err);
    }
  };

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
              {indexingStatus && (
                <button
                  onClick={handlePauseResumeIndexing}
                  className={`btn-pill ${indexingStatus.paused ? "paused" : ""}`}
                  title={indexingStatus.paused ? "Resume indexing" : "Pause indexing"}
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  {indexingStatus.paused ? (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none" />
                      </svg>
                      Resume
                    </>
                  ) : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="6" y="4" width="4" height="16" />
                        <rect x="14" y="4" width="4" height="16" />
                      </svg>
                      Pause
                    </>
                  )}
                </button>
              )}
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
              
              {/* More menu dropdown */}
              <div className="more-menu-container" style={{ position: "relative" }}>
                <button
                  onClick={() => setShowMoreMenu(!showMoreMenu)}
                  className={`btn-pill ${(showAnalytics || showLogs || showSettings || showPrivacy) ? "active" : ""}`}
                  title="More options"
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <MoreIcon />
                  More
                </button>
                
                {showMoreMenu && (
                  <div
                    style={{
                      position: "absolute",
                      top: "calc(100% + 8px)",
                      right: 0,
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-color)",
                      borderRadius: 8,
                      boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                      minWidth: 180,
                      zIndex: 1000,
                      overflow: "hidden",
                    }}
                  >
                    <button
                      onClick={() => {
                        setShowAnalytics(!showAnalytics);
                        setShowLogs(false);
                        setShowFaces(false);
                        setShowSettings(false);
                        setShowPrivacy(false);
                        setShowMoreMenu(false);
                      }}
                      style={{
                        width: "100%",
                        padding: "10px 16px",
                        textAlign: "left",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        border: "none",
                        background: showAnalytics ? "var(--bg-hover)" : "transparent",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                      onMouseEnter={(e) => {
                        if (!showAnalytics) {
                          e.currentTarget.style.background = "var(--bg-hover)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!showAnalytics) {
                          e.currentTarget.style.background = "transparent";
                        }
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
                        setShowMoreMenu(false);
                      }}
                      style={{
                        width: "100%",
                        padding: "10px 16px",
                        textAlign: "left",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        border: "none",
                        background: showLogs ? "var(--bg-hover)" : "transparent",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                      onMouseEnter={(e) => {
                        if (!showLogs) {
                          e.currentTarget.style.background = "var(--bg-hover)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!showLogs) {
                          e.currentTarget.style.background = "transparent";
                        }
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
                        setShowMoreMenu(false);
                      }}
                      style={{
                        width: "100%",
                        padding: "10px 16px",
                        textAlign: "left",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        border: "none",
                        background: showSettings ? "var(--bg-hover)" : "transparent",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                      onMouseEnter={(e) => {
                        if (!showSettings) {
                          e.currentTarget.style.background = "var(--bg-hover)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!showSettings) {
                          e.currentTarget.style.background = "transparent";
                        }
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
                        setShowMoreMenu(false);
                      }}
                      style={{
                        width: "100%",
                        padding: "10px 16px",
                        textAlign: "left",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        border: "none",
                        background: showPrivacy ? "var(--bg-hover)" : "transparent",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                      onMouseEnter={(e) => {
                        if (!showPrivacy) {
                          e.currentTarget.style.background = "var(--bg-hover)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!showPrivacy) {
                          e.currentTarget.style.background = "transparent";
                        }
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z" />
                      </svg>
                      Privacy
                    </button>
                  </div>
                )}
              </div>
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
          {status === "connected" && offlineMode && (
            <div
              className="status-badge no-network"
              title="Offline mode enabled - no network requests allowed"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 10px",
                fontSize: 12,
                fontWeight: 500,
                background: "var(--status-warning)",
                color: "var(--bg-primary)",
                borderRadius: 12,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              No Network
            </div>
          )}
          <StatusBadge 
            status={status} 
            wsConnected={wsConnected}
            health={health}
            onClick={() => {
              if (status === "connected" && health) {
                setShowHealthDetails(true);
              }
            }}
          />
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
            <h2>FFmpeg Not Found</h2>
            <p style={{ maxWidth: 480, lineHeight: 1.6 }}>
              SafeKeeps Vault requires FFmpeg to process video files. FFmpeg should be included with the application bundle.
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
                Repair Options
              </h3>

              <div style={{ marginBottom: 16 }}>
                <strong style={{ fontSize: 13 }}>Expected location:</strong>
                <code style={{
                  display: "block",
                  background: "var(--bg-primary)",
                  padding: "8px 12px",
                  borderRadius: 4,
                  marginTop: 6,
                  fontSize: 12,
                  fontFamily: "monospace"
                }}>
                  {process.platform === "win32" 
                    ? "App bundle binaries folder (ffmpeg.exe, ffprobe.exe)"
                    : "App bundle binaries folder (ffmpeg, ffprobe)"}
                </code>
              </div>

              <div style={{ 
                marginTop: 16, 
                padding: 12, 
                background: "var(--bg-primary)", 
                borderRadius: 4,
                fontSize: 12
              }}>
                <p style={{ marginBottom: 8, fontWeight: 500 }}><strong>If FFmpeg is still missing:</strong></p>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  <li>The application bundle may be corrupted</li>
                  <li>Antivirus software may have quarantined the binaries</li>
                  <li>You may be running a development build without bundled binaries</li>
                </ul>
                <p style={{ marginTop: 12, marginBottom: 0 }}>
                  <strong>Fallback:</strong> You can install FFmpeg system-wide and SafeKeeps Vault will use it from PATH.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
              <button
                className="btn btn-primary"
                onClick={() => window.location.reload()}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                Re-check FFmpeg
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowHealthDetails(true);
                }}
              >
                Open Diagnostics
              </button>
            </div>
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

        {showHealthDetails && health && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0, 0, 0, 0.5)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
            }}
            onClick={() => setShowHealthDetails(false)}
          >
            <div
              style={{
                background: "var(--bg-primary)",
                borderRadius: 12,
                padding: 24,
                maxWidth: 600,
                maxHeight: "80vh",
                overflow: "auto",
                boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <h2 style={{ margin: 0 }}>Health Details</h2>
                <button
                  onClick={() => setShowHealthDetails(false)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 4,
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
              
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <strong>Status:</strong> {health.status}
                </div>
                <div>
                  <strong>Models Ready:</strong> {health.models_ready ? "Yes" : "No"}
                  {!health.models_ready && health.missing_models && (
                    <div style={{ marginTop: 4, fontSize: 14, color: "var(--text-secondary)" }}>
                      Missing: {health.missing_models.join(", ")}
                    </div>
                  )}
                </div>
                
                {health.dependencies && (
                  <>
                    <div>
                      <strong>FFmpeg:</strong> {health.dependencies.ffmpeg_available ? "Available" : "Not found"}
                      {health.dependencies.ffmpeg_version && (
                        <span style={{ marginLeft: 8, fontSize: 14, color: "var(--text-secondary)" }}>
                          ({health.dependencies.ffmpeg_version})
                        </span>
                      )}
                    </div>
                    <div>
                      <strong>FFprobe:</strong> {health.dependencies.ffprobe_available ? "Available" : "Not found"}
                      {health.dependencies.ffprobe_version && (
                        <span style={{ marginLeft: 8, fontSize: 14, color: "var(--text-secondary)" }}>
                          ({health.dependencies.ffprobe_version})
                        </span>
                      )}
                    </div>
                    <div>
                      <strong>GPU:</strong> {health.dependencies.gpu_available ? "Available" : "Not available"}
                      {health.dependencies.gpu_name && (
                        <div style={{ marginTop: 4, fontSize: 14, color: "var(--text-secondary)" }}>
                          {health.dependencies.gpu_name}
                          {health.dependencies.gpu_memory_mb && (
                            <span> ({Math.round(health.dependencies.gpu_memory_mb / 1024)} GB)</span>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                )}
                
                <div>
                  <strong>Uptime:</strong> {Math.round(health.uptime_ms / 1000 / 60)} minutes
                </div>
                <div>
                  <strong>Engine UUID:</strong> <code style={{ fontSize: 12 }}>{health.engine_uuid}</code>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function StatusBadge({
  status,
  wsConnected,
  health,
  onClick
}: {
  status: "connected" | "disconnected" | "starting";
  wsConnected: boolean;
  health?: any;
  onClick?: () => void;
}) {
  const labels = {
    connected: "Ready",
    disconnected: "Offline",
    starting: "Starting",
  };

  return (
    <div className="status-badges">
      <div 
        className={`status-badge ${status} ${onClick ? "clickable" : ""}`} 
        title={status === "connected" ? "Click for health details" : undefined}
        onClick={onClick}
        style={onClick ? { cursor: "pointer" } : undefined}
      >
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
