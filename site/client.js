// One function per API route over fetch. The base URL is the only thing the site knows
// about the backend: localhost when the page is served locally, the production backend
// (the Cloudflare tunnel in front of `manc api`) when it is served from GitHub Pages, and
// whatever the header field set, kept in storage, over both.

export const DEFAULT_API_URL = "http://localhost:8000";
export const PRODUCTION_API_URL = ""; // the tunnel hostname; empty keeps localhost everywhere
const STORAGE_KEY = "manc.apiUrl";
const LOCAL_HOSTS = new Set(["", "localhost", "127.0.0.1", "[::1]"]);

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function storageOrNull() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function defaultApiUrl(hostname) {
  if (LOCAL_HOSTS.has(hostname) || !PRODUCTION_API_URL) {
    return DEFAULT_API_URL;
  }
  return PRODUCTION_API_URL;
}

export function apiUrl(storage = storageOrNull(), hostname = globalThis.location?.hostname ?? "") {
  const stored = storage?.getItem(STORAGE_KEY);
  return stored || defaultApiUrl(hostname);
}

export function setApiUrl(url, storage = storageOrNull()) {
  const trimmed = (url ?? "").trim().replace(/\/+$/, "");
  if (trimmed) {
    storage?.setItem(STORAGE_KEY, trimmed);
  } else {
    storage?.removeItem(STORAGE_KEY);
  }
}

export function buildUrl(base, path, params = {}) {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(name, String(value));
    }
  }
  const suffix = query.toString();
  return `${base}${path}${suffix ? `?${suffix}` : ""}`;
}

export function createClient({ fetch = globalThis.fetch, baseUrl = apiUrl } = {}) {
  async function get(path, params = {}) {
    const url = buildUrl(baseUrl(), path, params);
    let response;
    try {
      response = await fetch(url);
    } catch (error) {
      throw new ApiError(`cannot reach ${baseUrl()} (${error.message})`, null);
    }
    if (!response.ok) {
      let detail = `${response.status} from ${url}`;
      try {
        const body = await response.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // no JSON body: keep the status line
      }
      throw new ApiError(detail, response.status);
    }
    return response.json();
  }

  return {
    assets: () => get("/api/v1/assets"),
    overview: (params) => get("/api/v1/overview", params),
    scores: (symbol, params) => get(`/api/v1/assets/${symbol}/scores`, params),
    report: (symbol, params) => get(`/api/v1/assets/${symbol}/report`, params),
    headlines: (symbol, params) => get(`/api/v1/assets/${symbol}/headlines`, params),
    events: (params) => get("/api/v1/events", params),
    forecasts: (symbol, params) => get(`/api/v1/assets/${symbol}/forecasts`, params),
    spot: (symbol, params) => get(`/api/v1/assets/${symbol}/spot`, params),
    macroForecasts: (params) => get("/api/v1/macro/forecasts", params),
    formulas: () => get("/api/v1/formulas"),
    health: () => get("/health"),
  };
}
