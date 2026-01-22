import { useState, useEffect, useRef } from "react";

const TerminalIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </svg>
);

const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

const DownloadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

interface LogEntry {
  line: string;
  line_number: number;
}

interface LogsResponse {
  entries: LogEntry[];
  total_lines: number;
  file_path: string;
}

interface LogViewerProps {
  port: number;
}

export function LogViewer({ port }: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState(200);
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        lines: lines.toString(),
        tail: "true",
      });
      if (levelFilter) {
        params.append("level", levelFilter);
      }

      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<LogsResponse>(`/logs?${params}`);
      setLogs(data.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [port, lines, levelFilter]);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 2000); // Refresh every 2 seconds
      return () => clearInterval(interval);
    }
  }, [autoRefresh, port, lines, levelFilter]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (logContainerRef.current && autoRefresh) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoRefresh]);

  const getLogLevelColor = (line: string) => {
    if (line.includes("| ERROR")) return "#f87171";
    if (line.includes("| WARNING")) return "#fbbf24";
    if (line.includes("| INFO")) return "#60a5fa";
    if (line.includes("| DEBUG")) return "#a78bfa";
    return "";
  };

  const downloadLogs = () => {
    const content = logs.map((entry) => entry.line).join("\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `safekeeps-vault-logs-${new Date().toISOString().slice(0, 10)}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="log-viewer">
      <div className="log-viewer-header">
        <div className="log-viewer-title">
          <TerminalIcon />
          <span>Engine Logs</span>
        </div>
        <div className="log-viewer-controls">
          <select
            value={lines}
            onChange={(e) => setLines(Number(e.target.value))}
            className="log-filter"
          >
            <option value={100}>Last 100 lines</option>
            <option value={200}>Last 200 lines</option>
            <option value={500}>Last 500 lines</option>
            <option value={1000}>Last 1000 lines</option>
          </select>
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="log-filter"
          >
            <option value="">All levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <button
            className="btn-icon"
            onClick={fetchLogs}
            title="Refresh logs"
            disabled={loading}
          >
            <RefreshIcon />
          </button>
          <button
            className={`btn-icon ${autoRefresh ? "active" : ""}`}
            onClick={() => setAutoRefresh(!autoRefresh)}
            title="Auto-refresh"
          >
            <div className={`auto-refresh-indicator ${autoRefresh ? "pulsing" : ""}`} />
          </button>
          <button className="btn-icon" onClick={downloadLogs} title="Download logs">
            <DownloadIcon />
          </button>
        </div>
      </div>

      {error && (
        <div className="log-error">
          Error loading logs: {error}
        </div>
      )}

      <div className="log-container" ref={logContainerRef}>
        {loading && logs.length === 0 ? (
          <div className="log-loading">Loading logs...</div>
        ) : logs.length === 0 ? (
          <div className="log-empty">No logs found</div>
        ) : (
          <div className="log-content">
            {logs.map((entry) => (
              <div
                key={entry.line_number}
                className="log-line"
                style={{ color: getLogLevelColor(entry.line) || undefined }}
              >
                <span className="log-line-number">{entry.line_number}</span>
                <span className="log-line-text">{entry.line}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
