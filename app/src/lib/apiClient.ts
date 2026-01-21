/**
 * API client utility for making authenticated HTTP requests to the engine.
 * Automatically includes bearer token and resolves engine port in Tauri.
 */

// Check if we're running in Tauri
const isTauri = typeof window !== "undefined" && "__TAURI__" in window;

let cachedToken: string | null = null;
let cachedPort: number | null = null;

/**
 * Get the engine authentication token.
 * In Tauri, retrieves from Rust backend; otherwise returns null (web mode).
 */
async function getAuthToken(): Promise<string | null> {
  // Cache token to avoid repeated Tauri calls
  if (cachedToken) {
    return cachedToken;
  }

  if (isTauri) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      cachedToken = await invoke<string>("get_engine_token");
      return cachedToken;
    } catch (err) {
      console.error("[API] Failed to get token:", err);
      return null;
    }
  }

  // Web mode - no token available (assumes engine running without auth in dev)
  return null;
}

/**
 * Get the engine port from the Rust backend (Tauri only).
 */
async function getEnginePort(): Promise<number> {
  if (cachedPort) {
    return cachedPort;
  }

  if (isTauri) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      cachedPort = await invoke<number>("get_engine_port");
      return cachedPort;
    } catch (err) {
      console.error("[API] Failed to get port:", err);
    }
  }

  return 48100;
}

/**
 * Get base URL for engine API (resolves dynamic port in Tauri).
 */
export async function getApiBaseUrl(): Promise<string> {
  const port = await getEnginePort();
  return `http://127.0.0.1:${port}`;
}

/**
 * Make an authenticated HTTP request to the engine API.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const canRetry =
    options.body == null ||
    typeof options.body === "string" ||
    (typeof FormData !== "undefined" && options.body instanceof FormData) ||
    (typeof URLSearchParams !== "undefined" &&
      options.body instanceof URLSearchParams);

  let attempt = 0;
  while (true) {
    const port = await getEnginePort();
    const token = await getAuthToken();

    const isFormData =
      typeof FormData !== "undefined" && options.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> | undefined),
    };
    if (!isFormData && !("Content-Type" in headers)) {
      headers["Content-Type"] = "application/json";
    }

    // Add bearer token if available
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const url = `http://127.0.0.1:${port}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401 && attempt === 0 && canRetry) {
      clearAuthToken();
      attempt += 1;
      continue;
    }

    if (!response.ok) {
      const errorText = await response.text().catch(() => response.statusText);
      throw new Error(`API request failed: ${response.status} ${errorText}`);
    }

    // Return JSON if content type is JSON, otherwise return text
    const contentType = response.headers.get("content-type");
    if (contentType?.includes("application/json")) {
      return (await response.json()) as T;
    }

    return (await response.text()) as T;
  }
}

/**
 * Clear cached token (useful when engine restarts).
 */
export function clearAuthToken(): void {
  cachedToken = null;
}

/**
 * Clear cached API settings (token + port).
 */
export function clearApiCache(): void {
  cachedToken = null;
  cachedPort = null;
}
