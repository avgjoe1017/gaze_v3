import { useState, useEffect, useCallback, useRef } from "react";

type MessageType =
  | "heartbeat"
  | "pong"
  | "model_download_progress"
  | "model_download_complete"
  | "scan_progress"
  | "scan_complete"
  | "job_progress"
  | "job_complete"
  | "job_failed";

interface BaseMessage {
  type: MessageType;
}

interface ModelDownloadProgress extends BaseMessage {
  type: "model_download_progress";
  model: string;
  progress: number;
  bytes_downloaded: number;
  bytes_total: number;
}

interface ModelDownloadComplete extends BaseMessage {
  type: "model_download_complete";
  model: string;
}

interface ScanProgress extends BaseMessage {
  type: "scan_progress";
  library_id: string;
  files_found: number;
  files_new: number;
  files_changed: number;
  files_deleted: number;
}

interface ScanComplete extends BaseMessage {
  type: "scan_complete";
  library_id: string;
  files_found: number;
  files_new: number;
  files_changed: number;
  files_deleted: number;
}

interface JobProgress extends BaseMessage {
  type: "job_progress";
  job_id: string;
  video_id: string;
  stage: string;
  progress: number;
  message: string;
}

interface JobComplete extends BaseMessage {
  type: "job_complete";
  job_id: string;
  video_id: string;
}

interface JobFailed extends BaseMessage {
  type: "job_failed";
  job_id: string;
  video_id: string;
  stage: string;
  error_code: string;
  error_message: string;
}

type WebSocketMessage =
  | BaseMessage
  | ModelDownloadProgress
  | ModelDownloadComplete
  | ScanProgress
  | ScanComplete
  | JobProgress
  | JobComplete
  | JobFailed;

type MessageHandler = (message: WebSocketMessage) => void;

interface UseWebSocketOptions {
  port: number | null;
  enabled?: boolean;
}

export function useWebSocket({ port, enabled = true }: UseWebSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Set<MessageHandler>>(new Set());
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addHandler = useCallback((handler: MessageHandler) => {
    handlersRef.current.add(handler);
    return () => handlersRef.current.delete(handler);
  }, []);

  const connect = useCallback(async () => {
    if (!port || !enabled) return;

    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Get auth token if in Tauri
    let token: string | null = null;
    const isTauri = typeof window !== "undefined" && "__TAURI__" in window;
    if (isTauri) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        token = await invoke<string>("get_engine_token");
      } catch (err) {
        console.error("[WS] Failed to get token:", err);
      }
    }

    // Build WebSocket URL with token in query string
    let wsUrl = `ws://127.0.0.1:${port}/ws`;
    if (token) {
      // Use query string as fallback (protocol header not easily set in browser API)
      wsUrl += `?token=${encodeURIComponent(token)}`;
    }

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log("[WS] Connected");
        setConnected(true);

        // Send subscription message
        ws.send(JSON.stringify({ type: "subscribe", topics: ["*"] }));

        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage;

          // Skip heartbeat/pong for handlers
          if (message.type !== "heartbeat" && message.type !== "pong") {
            handlersRef.current.forEach((handler) => handler(message));
          }
        } catch (err) {
          console.error("[WS] Failed to parse message:", err);
        }
      };

      ws.onclose = () => {
        console.log("[WS] Disconnected");
        setConnected(false);

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Reconnect after delay
        if (enabled) {
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = (err) => {
        console.error("[WS] Error:", err);
      };

      wsRef.current = ws;
    } catch (err) {
      console.error("[WS] Failed to connect:", err);
      // Retry after delay
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    }
  }, [port, enabled]);

  // Connect when port changes
  useEffect(() => {
    if (port && enabled) {
      connect();
    }

    return () => {
      // Cleanup
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [port, enabled, connect]);

  return {
    connected,
    addHandler,
  };
}

// Hook for model download progress
export function useModelDownloadProgress(addHandler: (h: MessageHandler) => () => void) {
  const [downloads, setDownloads] = useState<Map<string, ModelDownloadProgress>>(new Map());

  useEffect(() => {
    return addHandler((msg) => {
      if (msg.type === "model_download_progress") {
        const progressMsg = msg as ModelDownloadProgress;
        setDownloads((prev) => new Map(prev).set(progressMsg.model, progressMsg));
      } else if (msg.type === "model_download_complete") {
        const completeMsg = msg as ModelDownloadComplete;
        setDownloads((prev) => {
          const next = new Map(prev);
          next.delete(completeMsg.model);
          return next;
        });
      }
    });
  }, [addHandler]);

  return downloads;
}

// Hook for scan progress
export function useScanProgress(addHandler: (h: MessageHandler) => () => void) {
  const [scans, setScans] = useState<Map<string, ScanProgress | ScanComplete>>(new Map());

  useEffect(() => {
    return addHandler((msg) => {
      if (msg.type === "scan_progress") {
        const scanMsg = msg as ScanProgress;
        setScans((prev) => new Map(prev).set(scanMsg.library_id, scanMsg));
      } else if (msg.type === "scan_complete") {
        const completeMsg = msg as ScanComplete;
        setScans((prev) => new Map(prev).set(completeMsg.library_id, completeMsg));
      }
    });
  }, [addHandler]);

  return scans;
}

// Hook for job progress
export function useJobProgress(addHandler: (h: MessageHandler) => () => void) {
  const [jobs, setJobs] = useState<Map<string, JobProgress | JobComplete | JobFailed>>(new Map());

  useEffect(() => {
    return addHandler((msg) => {
      if (msg.type === "job_progress" || msg.type === "job_complete" || msg.type === "job_failed") {
        const jobMsg = msg as JobProgress | JobComplete | JobFailed;
        setJobs((prev) => new Map(prev).set(jobMsg.job_id, jobMsg));
      }
    });
  }, [addHandler]);

  return jobs;
}
