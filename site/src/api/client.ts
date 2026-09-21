// One function per API route over fetch, against the page's own origin: `manc api` serves
// the site, and `npm run dev` proxies the API paths to it. A login in front of the origin
// (Cloudflare Access on the tunnel) covers page and requests alike.
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

export class ApiError extends Error {
  status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

export interface ClientOptions {
  fetch?: Fetch;
  baseUrl?: () => string;
}

export function createClient({ fetch = (url, init) => globalThis.fetch(url, init), baseUrl = () => "" }: ClientOptions = {}) {
  async function get<T>(path: string, params: Params = {}): Promise<T> {
    const url = buildUrl(baseUrl(), path, params);
    let response: Response;
    try {
      response = await fetch(url);
    } catch (error) {
      throw new ApiError(`cannot reach ${url} (${(error as Error).message})`, null);
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
