import { useState, useEffect, useCallback, type ReactNode } from "react";

interface ModelDownloadProgress {
  model: string;
  progress: number;
  bytes_downloaded: number;
  bytes_total: number;
}

interface ModelDownloadProps {
  missingModels: string[];
  wsDownloads?: Map<string, ModelDownloadProgress>;
}

interface ModelInfo {
  id: string;
  name: string;
  description: string;
  size: string;
  icon: ReactNode;
}

const MODELS: ModelInfo[] = [
  {
    id: "whisper-base",
    name: "Whisper Base",
    description: "Speech recognition for transcribing audio from your videos",
    size: "~140 MB",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
    ),
  },
  {
    id: "openclip-vit-b-32",
    name: "OpenCLIP ViT-B/32",
    description: "Visual embeddings for semantic image search across frames",
    size: "~350 MB",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <polyline points="21 15 16 10 5 21" />
      </svg>
    ),
  },
  {
    id: "ssdlite320-mobilenet-v3",
    name: "SSDLite MobileNetV3",
    description: "Object detection to identify people, objects, and scenes",
    size: "~13 MB",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="1" y="5" width="22" height="14" rx="2" />
        <rect x="5" y="9" width="6" height="6" rx="1" strokeDasharray="2 1" />
        <rect x="13" y="9" width="6" height="6" rx="1" strokeDasharray="2 1" />
      </svg>
    ),
  },
];

export function ModelDownload({ missingModels, wsDownloads }: ModelDownloadProps) {
  const [downloading, setDownloading] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [completed, setCompleted] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Update progress from WebSocket if available
  useEffect(() => {
    if (!wsDownloads) return;

    wsDownloads.forEach((wsProgress, modelId) => {
      if (!downloading.has(modelId)) {
        setDownloading(d => new Set(d).add(modelId));
      }
      setProgress(p => ({ ...p, [modelId]: Math.round(wsProgress.progress * 100) }));
    });

    // Check if any previously downloading models are no longer in wsDownloads (completed)
    downloading.forEach(modelId => {
      if (!wsDownloads.has(modelId) && progress[modelId] > 0) {
        setCompleted(c => c.includes(modelId) ? c : [...c, modelId]);
        setDownloading(d => {
          const newSet = new Set(d);
          newSet.delete(modelId);
          return newSet;
        });
        setProgress(p => ({ ...p, [modelId]: 100 }));
      }
    });
  }, [wsDownloads, downloading, progress]);

  // Poll for download progress
  const pollProgress = useCallback(async (modelId: string) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      return await apiRequest<{ status: string; progress?: number; error?: string }>(
        `/models/${encodeURIComponent(modelId)}/progress`
      );
    } catch {
      return null;
    }
  }, []);

  // Poll active downloads
  useEffect(() => {
    if (downloading.size === 0) return;

    const interval = setInterval(async () => {
      for (const modelId of downloading) {
        const status = await pollProgress(modelId);
        if (!status) continue;

        if (status.status === "complete") {
          setCompleted((c) => [...c, modelId]);
          setDownloading((d) => {
            const newSet = new Set(d);
            newSet.delete(modelId);
            return newSet;
          });
          setProgress((p) => ({ ...p, [modelId]: 100 }));
        } else if (status.status === "downloading") {
          setProgress((p) => ({ ...p, [modelId]: Math.round((status.progress ?? 0) * 100) }));
        } else if (status.status === "error") {
          setError(`${modelId}: ${status.error}`);
          setDownloading((d) => {
            const newSet = new Set(d);
            newSet.delete(modelId);
            return newSet;
          });
        }
      }
    }, 500);

    return () => clearInterval(interval);
  }, [downloading, pollProgress]);

  const downloadModel = async (modelId: string) => {
    setError(null);
    setProgress((p) => ({ ...p, [modelId]: 0 }));

    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ status: string }>("/models", {
        method: "POST",
        body: JSON.stringify({ model: modelId }),
      });

      if (data.status === "already_downloaded") {
        setCompleted((c) => [...c, modelId]);
        setProgress((p) => ({ ...p, [modelId]: 100 }));
      } else if (data.status === "started" || data.status === "downloading") {
        setDownloading((d) => new Set(d).add(modelId));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  };

  const downloadAll = async () => {
    for (const model of MODELS) {
      if (missingModels.includes(model.id) && !completed.includes(model.id)) {
        await downloadModel(model.id);
      }
    }
  };

  const isModelMissing = (id: string) => missingModels.includes(id) && !completed.includes(id);
  const allComplete = MODELS.every((m) => !isModelMissing(m.id));
  const anyDownloading = downloading.size > 0;

  return (
    <div className="model-download">
      <div className="model-grid">
        {MODELS.map((model, index) => {
          const isDownloading = downloading.has(model.id);
          const isComplete = completed.includes(model.id) || !missingModels.includes(model.id);
          const modelProgress = progress[model.id] || 0;

          return (
            <div
              key={model.id}
              className={`model-card ${isDownloading ? "downloading" : ""} ${isComplete ? "complete" : ""}`}
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className={`model-icon ${isComplete ? "complete" : ""}`}>
                {isComplete ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  model.icon
                )}
              </div>
              <div className="model-content">
                <div className="model-header">
                  <span className="model-name">{model.name}</span>
                  <span className="model-size">{model.size}</span>
                </div>
                <p className="model-description">{model.description}</p>

                <div className="model-status">
                  {isComplete ? (
                    <div className="model-status-complete">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Ready
                    </div>
                  ) : isDownloading ? (
                    <>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${modelProgress}%` }} />
                      </div>
                      <div className="progress-text">
                        <span>Downloading...</span>
                        <span>{modelProgress}%</span>
                      </div>
                    </>
                  ) : (
                    <button
                      className="btn btn-secondary"
                      onClick={() => downloadModel(model.id)}
                      disabled={anyDownloading}
                      style={{ padding: "8px 16px", fontSize: "13px" }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      Download
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {error && (
        <div style={{ color: "var(--status-error)", fontSize: 13, marginTop: 16, textAlign: "center" }}>
          {error}
        </div>
      )}

      <div className="download-actions">
        {!allComplete && (
          <button
            className="btn btn-primary"
            onClick={downloadAll}
            disabled={anyDownloading}
          >
            {anyDownloading ? (
              <>
                <div className="spinner" style={{ width: 16, height: 16 }} />
                Downloading...
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download All Models
              </>
            )}
          </button>
        )}

        {allComplete && (
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Continue to App
          </button>
        )}
      </div>
    </div>
  );
}
