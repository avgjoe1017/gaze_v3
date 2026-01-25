import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../lib/apiClient";

interface NetworkRequestEntry {
  kind: string;
  model: string | null;
  url: string;
  status: string;
  attempt: number | null;
  error: string | null;
  timestamp_ms: number;
}

interface NetworkStatusResponse {
  offline_mode: boolean;
  outbound_requests_total: number;
  model_downloads_total: number;
  recent_requests: NetworkRequestEntry[];
}

interface WipeDerivedResponse {
  status: string;
  message: string;
}

interface PrivacyViewProps {
  offlineMode: boolean;
  onUpdate: (update: { offline_mode: boolean }) => Promise<void>;
}

const ShieldIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export function PrivacyView({ offlineMode, onUpdate }: PrivacyViewProps) {
  const [network, setNetwork] = useState<NetworkStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wiping, setWiping] = useState(false);
  const [wipeStatus, setWipeStatus] = useState<string | null>(null);
  const [copyingReport, setCopyingReport] = useState(false);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<NetworkStatusResponse>("/network/status");
      setNetwork(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load network status");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleNetworkingToggle = useCallback(async () => {
    setError(null);
    try {
      await onUpdate({ offline_mode: !offlineMode });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update networking setting");
    }
  }, [offlineMode, onUpdate]);

  const handleWipeDerived = useCallback(async () => {
    setError(null);
    setWipeStatus(null);
    const confirmed = window.confirm(
      "Wipe derived data? This removes transcripts, thumbnails, detections, faces, and indexes. Media files stay intact."
    );
    if (!confirmed) return;
    setWiping(true);
    try {
      const data = await apiRequest<WipeDerivedResponse>("/maintenance/wipe-derived", { method: "POST" });
      setWipeStatus(data.message || "Derived data wiped. Re-scan libraries to rebuild indexes.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to wipe derived data");
    } finally {
      setWiping(false);
    }
  }, []);

  const handleWipeFaces = useCallback(async () => {
    setError(null);
    setWipeStatus(null);
    const confirmed = window.confirm(
      "Wipe face recognition data? This removes all face detections, person assignments, and face crops. " +
      "Media files and other derived data (transcripts, thumbnails) stay intact."
    );
    if (!confirmed) return;
    setWiping(true);
    try {
      const data = await apiRequest<WipeDerivedResponse>("/maintenance/wipe-faces", { method: "POST" });
      setWipeStatus(data.message || "Face data wiped.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to wipe face data");
    } finally {
      setWiping(false);
    }
  }, []);

  const handleCopyPrivacyReport = useCallback(async () => {
    setError(null);
    setCopyingReport(true);
    try {
      const data = await apiRequest<{ report: string }>("/network/privacy-report");
      await navigator.clipboard.writeText(data.report);
      setWipeStatus("Privacy report copied to clipboard");
      setTimeout(() => setWipeStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to copy privacy report");
    } finally {
      setCopyingReport(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 6000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const requests = useMemo(() => {
    if (!network?.recent_requests) return [];
    return [...network.recent_requests].sort((a, b) => b.timestamp_ms - a.timestamp_ms);
  }, [network]);

  return (
    <div className="privacy-container">
      <div className="privacy-hero">
        <div className="privacy-kicker">
          <ShieldIcon />
          Trust Ledger
        </div>
        <h2>Private by default. Verifiable every session.</h2>
        <p>
          SafeKeeps Vault runs on your device, keeps media local, and shows the only outbound requests it makes.
          You can lock networking off entirely.
        </p>
        <div className="privacy-actions">
          <button className="btn btn-secondary" onClick={fetchStatus} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh Status"}
          </button>
          <div className="privacy-toggle">
            <div>
              <div className="privacy-toggle-label">Disable networking</div>
              <div className="privacy-toggle-note">Blocks model downloads and any outbound requests.</div>
            </div>
            <button
              className={`toggle-switch ${offlineMode ? "active" : ""}`}
              onClick={handleNetworkingToggle}
              aria-pressed={offlineMode}
            >
              <span />
            </button>
          </div>
        </div>
        {error && <div className="privacy-alert">{error}</div>}
      </div>

      <div className="privacy-grid">
        <div className="privacy-card">
          <h3>Local-only proof</h3>
          <ul className="privacy-checklist">
            <li>
              <span className="privacy-check">✓</span>
              Media never uploaded — files stay on this device.
            </li>
            <li>
              <span className="privacy-check">✓</span>
              Models run locally and can be blocked via offline mode.
            </li>
            <li>
              <span className="privacy-check">✓</span>
              Engine binds to 127.0.0.1 with per-session auth.
            </li>
            <li>
              <span className="privacy-check">✓</span>
              Face recognition is opt-in and can stay disabled.
            </li>
          </ul>
        </div>

        <div className="privacy-card">
          <h3>Outbound traffic (this session)</h3>
          <div className="privacy-stats">
            <div>
              <div className="privacy-stat-value">{network?.outbound_requests_total ?? 0}</div>
              <div className="privacy-stat-label">Outbound requests</div>
            </div>
            <div>
              <div className="privacy-stat-value">{network?.model_downloads_total ?? 0}</div>
              <div className="privacy-stat-label">Model downloads</div>
            </div>
            <div className={`privacy-pill ${offlineMode ? "locked" : "open"}`}>
              {offlineMode ? "Networking Locked" : "Networking Allowed"}
            </div>
          </div>
          <p className="privacy-note">
            If you see a request here, it should only be for model downloads you triggered.
          </p>
        </div>

        <div className="privacy-card">
          <h3>Privacy Report</h3>
          <p className="privacy-note">
            Copy a summary of network activity, models installed, and data location for verification.
          </p>
          <div className="privacy-wipe-actions">
            <button 
              className="btn btn-secondary" 
              onClick={handleCopyPrivacyReport} 
              disabled={copyingReport}
            >
              {copyingReport ? "Copying..." : "Copy Privacy Report"}
            </button>
          </div>
        </div>

        <div className="privacy-card">
          <h3>Derived data controls</h3>
          <p className="privacy-note">
            Clear transcripts, thumbnails, detections, face crops, and indexes. Media files are untouched.
          </p>
          <div className="privacy-wipe-actions">
            <button className="btn btn-secondary" onClick={handleWipeDerived} disabled={wiping}>
              {wiping ? "Wiping..." : "Wipe Derived Data"}
            </button>
          </div>
          {wipeStatus && <div className="privacy-wipe-status">{wipeStatus}</div>}
        </div>

        <div className="privacy-card">
          <h3>Face data controls</h3>
          <p className="privacy-note">
            Wipe only face recognition data (faces, person assignments, face crops). 
            Other derived data (transcripts, thumbnails, detections) remains intact.
          </p>
          <div className="privacy-wipe-actions">
            <button className="btn btn-secondary" onClick={handleWipeFaces} disabled={wiping}>
              {wiping ? "Wiping..." : "Wipe Faces Only"}
            </button>
          </div>
        </div>
      </div>

      <div className="privacy-card privacy-ledger">
        <div className="privacy-ledger-header">
          <div>
            <h3>Outbound ledger</h3>
            <span>Recent requests (since engine start)</span>
          </div>
          <button className="btn btn-ghost" onClick={fetchStatus} disabled={loading}>
            Reload
          </button>
        </div>
        {requests.length === 0 ? (
          <div className="privacy-empty">
            No outbound requests recorded for this session.
          </div>
        ) : (
          <div className="privacy-ledger-list">
            {requests.map((req, index) => (
              <div key={`${req.timestamp_ms}-${index}`} className={`privacy-ledger-row ${req.status}`}>
                <div className="privacy-ledger-time">
                  {new Date(req.timestamp_ms).toLocaleTimeString()}
                </div>
                <div className="privacy-ledger-main">
                  <div className="privacy-ledger-title">
                    {req.model ? req.model : req.kind}
                    {req.attempt ? <span>Attempt {req.attempt}</span> : null}
                  </div>
                  <div className="privacy-ledger-url">
                    {req.url.replace(/^https?:\/\//, "")}
                  </div>
                  {req.error && <div className="privacy-ledger-error">{req.error}</div>}
                </div>
                <div className={`privacy-ledger-status ${req.status}`}>
                  {req.status}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
