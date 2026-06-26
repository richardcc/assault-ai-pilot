const ENV_API_BASE = String(import.meta.env.VITE_API_BASE_URL || "").trim();
const ENV_API_PORT = String(import.meta.env.VITE_API_PORT || "8000").trim();

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export function getApiBaseUrl(): string {
  if (ENV_API_BASE) return ENV_API_BASE.replace(/\/+$/, "");
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:${ENV_API_PORT}`;
  }
  return `http://127.0.0.1:${ENV_API_PORT}`;
}

export function apiUrl(path: string): string {
  return `${getApiBaseUrl()}${normalizePath(path)}`;
}

export function wsUrl(path: string): string {
  const httpBase = getApiBaseUrl();
  const wsBase = httpBase.startsWith("https://")
    ? httpBase.replace("https://", "wss://")
    : httpBase.replace("http://", "ws://");
  return `${wsBase}${normalizePath(path)}`;
}

