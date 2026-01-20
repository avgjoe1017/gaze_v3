import { useState, useEffect, useCallback } from "react";

// Check if we're running in Tauri
const isTauri = typeof window !== "undefined" && "__TAURI__" in window;

interface DependencyStatus {
  ffmpeg_available: boolean;
  ffmpeg_version: string | null;
  ffprobe_available: boolean;
  ffprobe_version: string | null;
  gpu_available: boolean;
  gpu_name: string | null;
  gpu_memory_mb: number | null;
}

interface HealthResponse {
  status: "starting" | "ready" | "error";
  models_ready: boolean;
  missing_models: string[];
  dependencies: DependencyStatus;
  engine_uuid: string;
  uptime_ms: number;
}

interface EngineState {
  status: "connected" | "disconnected" | "starting";
  port: number | null;
  health: HealthResponse | null;
  error: string | null;
}

// Default port for web-only mode (engine must be started manually)
const DEFAULT_PORT = 48100;

export function useEngine() {
  const [state, setState] = useState<EngineState>({
    status: "disconnected",
    port: null,
    health: null,
    error: null,
  });

  const checkHealth = useCallback(async (port: number) => {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const health = (await res.json()) as HealthResponse;
      setState((s) => ({ ...s, status: "connected", port, health, error: null }));
      return true;
    } catch {
      return false;
    }
  }, []);

  const startEngine = useCallback(async () => {
    setState((s) => ({ ...s, status: "starting", error: null }));

    try {
      let port: number;

      if (isTauri) {
        // Running in Tauri - use invoke to start engine
        const { invoke } = await import("@tauri-apps/api/core");
        port = await invoke<number>("start_engine");
      } else {
        // Running in browser - assume engine is already running
        port = DEFAULT_PORT;
        console.log("Running in web mode - expecting engine on port", port);
      }

      setState((s) => ({ ...s, port }));

      // Poll for health with exponential backoff
      let delay = 100;
      const maxDelay = 2000;
      const deadline = Date.now() + 30000;

      while (Date.now() < deadline) {
        const healthy = await checkHealth(port);
        if (healthy) return;

        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, maxDelay);
      }

      throw new Error("Engine startup timeout - make sure engine is running on port " + port);
    } catch (err) {
      setState((s) => ({
        ...s,
        status: "disconnected",
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  }, [checkHealth]);

  const stopEngine = useCallback(async () => {
    if (isTauri) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("stop_engine");
      } catch (err) {
        console.error("Failed to stop engine:", err);
      }
    }
    setState((s) => ({ ...s, status: "disconnected", health: null }));
  }, []);

  // Auto-start engine on mount
  useEffect(() => {
    startEngine();

    // Cleanup on unmount (only in Tauri)
    return () => {
      if (isTauri) {
        stopEngine();
      }
    };
  }, [startEngine, stopEngine]);

  // Periodic health checks
  useEffect(() => {
    if (state.status !== "connected" || !state.port) return;

    const interval = setInterval(() => {
      checkHealth(state.port!);
    }, 5000);

    return () => clearInterval(interval);
  }, [state.status, state.port, checkHealth]);

  return {
    ...state,
    startEngine,
    stopEngine,
    refreshHealth: () => state.port && checkHealth(state.port),
  };
}
