// One function per API route over fetch. The base URL is the only thing the site knows
// about the backend: localhost when the page is served locally, the production backend
// (the Cloudflare tunnel in front of `manc api`) when it is served from GitHub Pages, and
// whatever the header field set, kept in storage, over both.
import type {
  AssetHistory,
  AssetOut,
  AssetSummary,
  CalendarEvent,
  ChainSeries,
  ForecastPanel,
  FormulasOut,
  HeadlineView,
  HealthOut,
  MacroForecastRow,
  Params,
  ReportOut,
  SpotPrice,
} from "./types";

export const DEFAULT_API_URL = "http://localhost:8000";
export const PRODUCTION_API_URL = ""; // the tunnel hostname; empty keeps localhost everywhere
const STORAGE_KEY = "manc.apiUrl";
const LOCAL_HOSTS = new Set(["", "localhost", "127.0.0.1", "[::1]"]);

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export class ApiError extends Error {
  status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function storageOrNull(): KeyValueStorage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function defaultApiUrl(hostname: string): string {
  if (LOCAL_HOSTS.has(hostname) || !PRODUCTION_API_URL) {
    return DEFAULT_API_URL;
  }
  return PRODUCTION_API_URL;
}

export function apiUrl(
  storage: KeyValueStorage | null = storageOrNull(),
  hostname: string = globalThis.location?.hostname ?? "",
): string {
  const stored = storage?.getItem(STORAGE_KEY);
  return stored || defaultApiUrl(hostname);
}

export function setApiUrl(url: string | null, storage: KeyValueStorage | null = storageOrNull()): void {
  const trimmed = (url ?? "").trim().replace(/\/+$/, "");
  if (trimmed) {
    storage?.setItem(STORAGE_KEY, trimmed);
  } else {
    storage?.removeItem(STORAGE_KEY);
  }
}

export function buildUrl(base: string, path: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(name, String(value));
    }
  }
  const suffix = query.toString();
  return `${base}${path}${suffix ? `?${suffix}` : ""}`;
}

type Fetch = (url: string) => Promise<Response>;

export interface ClientOptions {
  fetch?: Fetch;
  baseUrl?: () => string;
}

export function createClient({ fetch = (url) => globalThis.fetch(url), baseUrl = apiUrl }: ClientOptions = {}) {
  async function get<T>(path: string, params: Params = {}): Promise<T> {
    const url = buildUrl(baseUrl(), path, params);
    let response: Response;
    try {
      response = await fetch(url);
    } catch (error) {
      throw new ApiError(`cannot reach ${baseUrl()} (${(error as Error).message})`, null);
    }
    if (!response.ok) {
      let detail = `${response.status} from ${url}`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (body?.detail) detail = String(body.detail);
      } catch {
        // no JSON body: keep the status line
      }
      throw new ApiError(detail, response.status);
    }
    return response.json() as Promise<T>;
  }

  return {
    assets: () => get<AssetOut[]>("/api/v1/assets"),
    overview: (params: Params = {}) => get<AssetSummary[]>("/api/v1/overview", params),
    scores: (symbol: string, params: Params = {}) => get<AssetHistory>(`/api/v1/assets/${symbol}/scores`, params),
    report: (symbol: string, params: Params = {}) => get<ReportOut>(`/api/v1/assets/${symbol}/report`, params),
    headlines: (symbol: string, params: Params = {}) => get<HeadlineView[]>(`/api/v1/assets/${symbol}/headlines`, params),
    events: (params: Params = {}) => get<CalendarEvent[]>("/api/v1/events", params),
    forecasts: (symbol: string, params: Params = {}) => get<ForecastPanel>(`/api/v1/assets/${symbol}/forecasts`, params),
    spot: (symbol: string, params: Params = {}) => get<SpotPrice[]>(`/api/v1/assets/${symbol}/spot`, params),
    chain: (symbol: string, params: Params = {}) => get<ChainSeries[]>(`/api/v1/assets/${symbol}/chain`, params),
    macroForecasts: (params: Params = {}) => get<MacroForecastRow[]>("/api/v1/macro/forecasts", params),
    formulas: () => get<FormulasOut>("/api/v1/formulas"),
    health: () => get<HealthOut>("/health"),
  };
}

export type Client = ReturnType<typeof createClient>;
