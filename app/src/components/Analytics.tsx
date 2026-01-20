import { useState, useEffect } from "react";
import { apiRequest } from "../lib/apiClient";

interface StorageBreakdown {
  raw_videos_bytes: number;
  indexed_artifacts_bytes: number;
  thumbnails_bytes: number;
  faiss_shards_bytes: number;
  temp_files_bytes: number;
  database_bytes: number;
  total_bytes: number;
}

interface DatabaseStats {
  total_videos: number;
  indexed_videos: number;
  queued_videos: number;
  processing_videos: number;
  failed_videos: number;
  total_segments: number;
  total_frames: number;
  total_detections: number;
  total_libraries: number;
}

interface FormatBreakdown {
  container_format?: string | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  count: number;
  total_duration_ms?: number | null;
}

interface CodecStats {
  containers: FormatBreakdown[];
  video_codecs: FormatBreakdown[];
  audio_codecs: FormatBreakdown[];
}

interface LocationStats {
  videos_with_location: number;
  total_locations: number;
}

interface StatsResponse {
  storage: StorageBreakdown;
  database: DatabaseStats;
  codecs: CodecStats;
  location: LocationStats;
}

const BarChartIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="20" x2="12" y2="10" />
    <line x1="18" y1="20" x2="18" y2="4" />
    <line x1="6" y1="20" x2="6" y2="16" />
  </svg>
);

const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return "N/A";
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
}

export function Analytics() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStats = async () => {
    try {
      setError(null);
      const data = await apiRequest<StatsResponse>("/stats");
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load statistics");
      console.error("[Analytics] Failed to fetch stats:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStats();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchStats();
  };

  if (loading) {
    return (
      <div className="analytics-container">
        <div className="empty-state">
          <div className="spinner spinner-large" />
          <p>Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-container">
        <div className="empty-state">
          <div className="empty-state-icon" style={{ color: "var(--status-error)" }}>
            <BarChartIcon />
          </div>
          <h3>Failed to Load Analytics</h3>
          <p>{error}</p>
          <button className="btn btn-primary" onClick={handleRefresh} style={{ marginTop: 16 }}>
            <RefreshIcon />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const { storage, database, codecs, location } = stats;

  return (
    <div className="analytics-container">
      <div className="analytics-header">
        <div className="analytics-title">
          <BarChartIcon />
          <h2>Analytics Dashboard</h2>
        </div>
        <button
          className="btn-icon"
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh statistics"
        >
          <RefreshIcon />
        </button>
      </div>

      <div className="analytics-grid">
        {/* Storage Section */}
        <div className="analytics-card">
          <h3>Storage Usage</h3>
          <div className="storage-breakdown">
            <div className="storage-item">
              <div className="storage-label">Raw Media</div>
              <div className="storage-value">{formatBytes(storage.raw_videos_bytes)}</div>
              <div className="storage-bar">
                <div
                  className="storage-bar-fill"
                  style={{
                    width: `${(storage.raw_videos_bytes / storage.total_bytes) * 100}%`,
                    backgroundColor: "var(--accent)",
                  }}
                />
              </div>
            </div>
            <div className="storage-item">
              <div className="storage-label">Indexed Artifacts</div>
              <div className="storage-value">{formatBytes(storage.indexed_artifacts_bytes)}</div>
              <div className="storage-bar">
                <div
                  className="storage-bar-fill"
                  style={{
                    width: `${(storage.indexed_artifacts_bytes / storage.total_bytes) * 100}%`,
                    backgroundColor: "var(--status-info)",
                  }}
                />
              </div>
            </div>
            <div className="storage-details">
              <div className="storage-detail">
                <span>Thumbnails:</span>
                <span>{formatBytes(storage.thumbnails_bytes)}</span>
              </div>
              <div className="storage-detail">
                <span>FAISS Shards:</span>
                <span>{formatBytes(storage.faiss_shards_bytes)}</span>
              </div>
              <div className="storage-detail">
                <span>Temp Files:</span>
                <span>{formatBytes(storage.temp_files_bytes)}</span>
              </div>
              <div className="storage-detail">
                <span>Database:</span>
                <span>{formatBytes(storage.database_bytes)}</span>
              </div>
            </div>
            <div className="storage-total">
              <span>Total:</span>
              <span>{formatBytes(storage.total_bytes)}</span>
            </div>
          </div>
        </div>

        {/* Database Statistics */}
        <div className="analytics-card">
          <h3>Database Statistics</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">Total Items</div>
              <div className="stat-value">{database.total_videos.toLocaleString()}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Indexed</div>
              <div className="stat-value" style={{ color: "var(--status-success)" }}>
                {database.indexed_videos.toLocaleString()}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Queued</div>
              <div className="stat-value" style={{ color: "var(--status-warning)" }}>
                {database.queued_videos.toLocaleString()}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Processing</div>
              <div className="stat-value" style={{ color: "var(--status-info)" }}>
                {database.processing_videos.toLocaleString()}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Failed</div>
              <div className="stat-value" style={{ color: "var(--status-error)" }}>
                {database.failed_videos.toLocaleString()}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Transcript Segments</div>
              <div className="stat-value">{database.total_segments.toLocaleString()}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Frames</div>
              <div className="stat-value">{database.total_frames.toLocaleString()}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Detections</div>
              <div className="stat-value">{database.total_detections.toLocaleString()}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Libraries</div>
              <div className="stat-value">{database.total_libraries.toLocaleString()}</div>
            </div>
          </div>
        </div>

        {/* Format Breakdown */}
        <div className="analytics-card">
          <h3>Container Formats</h3>
          {codecs.containers.length > 0 ? (
            <div className="format-list">
              {codecs.containers.map((item, idx) => (
                <div key={idx} className="format-item">
                  <div className="format-name">{item.container_format || "Unknown"}</div>
                  <div className="format-count">{item.count} items</div>
                  {item.total_duration_ms && (
                    <div className="format-duration">{formatDuration(item.total_duration_ms)}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>No format data available</p>
          )}
        </div>

        {/* Video Codecs */}
        <div className="analytics-card">
          <h3>Video Codecs</h3>
          {codecs.video_codecs.length > 0 ? (
            <div className="format-list">
              {codecs.video_codecs.map((item, idx) => (
                <div key={idx} className="format-item">
                  <div className="format-name">{item.video_codec || "Unknown"}</div>
                  <div className="format-count">{item.count} items</div>
                  {item.total_duration_ms && (
                    <div className="format-duration">{formatDuration(item.total_duration_ms)}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>No codec data available</p>
          )}
        </div>

        {/* Audio Codecs */}
        <div className="analytics-card">
          <h3>Audio Codecs</h3>
          {codecs.audio_codecs.length > 0 ? (
            <div className="format-list">
              {codecs.audio_codecs.map((item, idx) => (
                <div key={idx} className="format-item">
                  <div className="format-name">{item.audio_codec || "Unknown"}</div>
                  <div className="format-count">{item.count} items</div>
                  {item.total_duration_ms && (
                    <div className="format-duration">{formatDuration(item.total_duration_ms)}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>No codec data available</p>
          )}
        </div>

        {/* Location Statistics */}
        {location.videos_with_location > 0 && (
          <div className="analytics-card">
            <h3>Location Data</h3>
            <div className="stats-grid">
              <div className="stat-item">
                <div className="stat-label">Items with GPS</div>
                <div className="stat-value">{location.videos_with_location.toLocaleString()}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Total Locations</div>
                <div className="stat-value">{location.total_locations.toLocaleString()}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
