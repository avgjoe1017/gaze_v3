import { useCallback, useMemo, useState } from "react";
import { apiRequest } from "../lib/apiClient";

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

interface BackupPayload {
  version: string;
  created_at_ms: number;
  settings: Record<string, unknown>;
  libraries: unknown[];
  media: unknown[];
  media_metadata: unknown[];
  videos: unknown[];
  video_metadata: unknown[];
  persons: unknown[];
}

interface SettingsViewProps {
  settings: SettingsData | null;
  loading: boolean;
  onRefresh: () => void;
  onUpdate: (update: Partial<SettingsData>) => Promise<void>;
}

const SettingsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.82-.33 1.7 1.7 0 0 0-1 1.54V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.54 1.7 1.7 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.54-1H3a2 2 0 1 1 0-4h.06a1.7 1.7 0 0 0 1.54-1 1.7 1.7 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 8 4.6a1.7 1.7 0 0 0 1-1.54V3a2 2 0 1 1 4 0v.06a1.7 1.7 0 0 0 1 1.54 1.7 1.7 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.33 1.82 1.7 1.7 0 0 0 1.54 1H21a2 2 0 1 1 0 4h-.06a1.7 1.7 0 0 0-1.54 1z" />
  </svg>
);

const DownloadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

export function SettingsView({ settings, loading, onRefresh, onUpdate }: SettingsViewProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreMode, setRestoreMode] = useState<"merge" | "replace">("merge");
  const [restoreStatus, setRestoreStatus] = useState<string | null>(null);

  const indexingPreset = settings?.indexing_preset ?? "deep";
  const numericDraft = useMemo(() => ({
    max_concurrent_jobs: settings?.max_concurrent_jobs ?? 2,
    frame_interval_seconds: settings?.frame_interval_seconds ?? 2,
    thumbnail_quality: settings?.thumbnail_quality ?? 85,
    faiss_cache_max: settings?.faiss_cache_max ?? 8,
  }), [settings]);

  const handleUpdate = useCallback(async (update: Partial<SettingsData>) => {
    setError(null);
    setSaving(true);
    try {
      await onUpdate(update);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update settings");
    } finally {
      setSaving(false);
    }
  }, [onUpdate]);

  const handleExport = useCallback(async () => {
    setError(null);
    try {
      const payload = await apiRequest<BackupPayload>("/backup/export");
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const date = new Date().toISOString().slice(0, 10);
      link.href = url;
      link.download = `safekeeps-vault-backup-${date}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export backup");
    }
  }, []);

  const handleRestore = useCallback(async () => {
    setError(null);
    setRestoreStatus(null);
    if (!restoreFile) {
      setError("Choose a backup file first.");
      return;
    }
    if (restoreMode === "replace") {
      const confirmed = window.confirm("Replace will overwrite current metadata. Continue?");
      if (!confirmed) return;
    }
    try {
      const text = await restoreFile.text();
      const payload = JSON.parse(text) as BackupPayload;
      await apiRequest(`/backup/restore?mode=${restoreMode}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setRestoreStatus("Restore complete. Re-scan libraries to rebuild indexes.");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore backup");
    }
  }, [onRefresh, restoreFile, restoreMode]);

  if (loading) {
    return (
      <div className="settings-container">
        <div className="empty-state">
          <div className="spinner spinner-large" />
          <p>Loading settings...</p>
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="settings-container">
        <div className="empty-state">
          <div className="empty-state-icon">
            <SettingsIcon />
          </div>
          <h3>Settings Unavailable</h3>
          <p>Unable to load settings from the engine.</p>
          <button className="btn btn-primary" onClick={onRefresh}>
            Refresh
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-container">
      <div className="settings-header">
        <div className="settings-title">
          <SettingsIcon />
          <h2>Settings</h2>
        </div>
        <button className="btn-icon" onClick={onRefresh} title="Refresh settings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      </div>

      {error && (
        <div className="settings-alert settings-alert-error">
          {error}
        </div>
      )}
      {saving && (
        <div className="settings-alert settings-alert-info">
          Saving settings...
        </div>
      )}
      {restoreStatus && (
        <div className="settings-alert settings-alert-success">
          {restoreStatus}
        </div>
      )}

      <div className="settings-grid">
        <div className="settings-card">
          <h3>Privacy & Offline</h3>
          <div className="setting-row">
            <div>
              <div className="setting-label">Disable Networking</div>
              <div className="setting-description">Blocks model downloads and any outbound requests.</div>
            </div>
            <button
              className={`toggle-switch ${settings.offline_mode ? "active" : ""}`}
              onClick={() => handleUpdate({ offline_mode: !settings.offline_mode })}
              aria-pressed={settings.offline_mode}
            >
              <span />
            </button>
          </div>

          <div className="setting-row">
            <div>
              <div className="setting-label">Face Recognition</div>
              <div className="setting-description">
                <strong>Faces are derived data.</strong> Face recognition runs locally and never leaves your device. 
                Face data can be fully removed at any time. This feature is opt-in and disabled by default.
              </div>
            </div>
            <button
              className={`toggle-switch ${settings.face_recognition_enabled ? "active" : ""}`}
              onClick={() => {
                if (!settings.face_recognition_enabled) {
                  const ok = window.confirm(
                    "Enable face recognition?\n\n" +
                    "• Faces are derived data (can be fully removed)\n" +
                    "• All processing happens locally\n" +
                    "• Face data never leaves your device\n" +
                    "• You can disable and wipe face data at any time"
                  );
                  if (!ok) return;
                }
                handleUpdate({ face_recognition_enabled: !settings.face_recognition_enabled });
              }}
              aria-pressed={settings.face_recognition_enabled}
            >
              <span />
            </button>
          </div>
        </div>

        <div className="settings-card">
          <h3>Indexing Performance</h3>
          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Indexing Preset</div>
              <div className="setting-description">Quick skips transcription and detections; Deep runs full analysis.</div>
            </div>
            <select
              value={indexingPreset}
              onChange={(e) => handleUpdate({ indexing_preset: e.target.value })}
            >
              <option value="quick">Quick</option>
              <option value="deep">Deep</option>
            </select>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Prioritize Recent Media</div>
              <div className="setting-description">Index most recently modified files first, so recent content becomes searchable sooner.</div>
            </div>
            <button
              className={`toggle-switch ${settings.prioritize_recent_media ? "active" : ""}`}
              onClick={() => handleUpdate({ prioritize_recent_media: !settings.prioritize_recent_media })}
              aria-pressed={settings.prioritize_recent_media}
            >
              <span />
            </button>
          </div>
          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Max Concurrent Jobs</div>
              <div className="setting-description">Limits how many media items are indexed at once.</div>
            </div>
            <input
              type="number"
              min={1}
              max={8}
              defaultValue={numericDraft.max_concurrent_jobs}
              onBlur={(e) => handleUpdate({ max_concurrent_jobs: Number(e.target.value) })}
            />
          </div>

          <div className="setting-row input-row">
            <div>
              <div className="setting-label">FAISS Cache Size</div>
              <div className="setting-description">How many visual indexes to keep in memory for faster search.</div>
            </div>
            <input
              type="number"
              min={1}
              max={32}
              defaultValue={numericDraft.faiss_cache_max}
              onBlur={(e) => handleUpdate({ faiss_cache_max: Number(e.target.value) })}
            />
          </div>

          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Frame Interval (seconds)</div>
              <div className="setting-description">How often to sample frames from videos.</div>
            </div>
            <input
              type="number"
              min={0.5}
              step={0.5}
              defaultValue={numericDraft.frame_interval_seconds}
              onBlur={(e) => handleUpdate({ frame_interval_seconds: Number(e.target.value) })}
            />
          </div>

          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Thumbnail Quality</div>
              <div className="setting-description">Controls JPEG quality for generated thumbnails.</div>
            </div>
            <input
              type="number"
              min={50}
              max={95}
              defaultValue={numericDraft.thumbnail_quality}
              onBlur={(e) => handleUpdate({ thumbnail_quality: Number(e.target.value) })}
            />
          </div>
        </div>

        <div className="settings-card">
          <h3>Backup & Restore</h3>
          <p className="settings-note">
            Backups store metadata only (settings, libraries, people). Media files are not included.
          </p>
          <div className="settings-actions">
            <button className="btn btn-primary" onClick={handleExport}>
              <DownloadIcon />
              Export Backup
            </button>
          </div>

          <div className="settings-divider" />

          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Restore Backup</div>
              <div className="setting-description">Import metadata from a previous backup file.</div>
            </div>
            <input
              type="file"
              accept="application/json"
              onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="setting-row input-row">
            <div>
              <div className="setting-label">Restore Mode</div>
              <div className="setting-description">Merge keeps existing data; replace overwrites.</div>
            </div>
            <select value={restoreMode} onChange={(e) => setRestoreMode(e.target.value as "merge" | "replace")}>
              <option value="merge">Merge</option>
              <option value="replace">Replace</option>
            </select>
          </div>

          <div className="settings-actions">
            <button className="btn btn-secondary" onClick={handleRestore}>
              <UploadIcon />
              Restore Backup
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
