import { describe, expect, test } from "vitest";

import { ApiError, buildUrl, createClient } from "../api/client";

function fakeFetch(responses: { status: number; body: unknown }[]) {
  const calls: string[] = [];
  const inits: RequestInit[] = [];
  const fetchFake = async (url: string, init: RequestInit = {}) => {
    calls.push(url);
    inits.push(init);
    const answer = responses[calls.length - 1] ?? { status: 200, body: {} };
    return { ok: answer.status < 300, status: answer.status, json: async () => answer.body } as Response;
  };
  return Object.assign(fetchFake, { calls, inits });
}

describe("buildUrl", () => {
  test("buildUrl encodes the params and drops the empty ones", () => {
    const url = buildUrl("http://localhost:8888", "/api/v1/events", {
      from: "2026-09-19",
      to: undefined,
      min_importance: 2,
      economy: null,
      metric: "",
    });
    expect(url).toBe("http://localhost:8888/api/v1/events?from=2026-09-19&min_importance=2");
    expect(buildUrl("http://x", "/health", {})).toBe("http://x/health");
  });
});

describe("client", () => {
  test("the requests go to the page's own origin: the API serves the site", async () => {
    const fetchFake = fakeFetch([]);
    const client = createClient({ fetch: fetchFake });
    await client.health();
    expect(fetchFake.calls).toEqual(["/health"]);
    expect(fetchFake.inits[0]?.credentials).toBeUndefined(); // same origin, the cookie rides along anyway
  });

  test("every route function hits its path with its query", async () => {
    const fetchFake = fakeFetch([]);
    const client = createClient({ fetch: fetchFake, baseUrl: () => "http://x" });
    await client.assets();
    await client.overview({ as_of: "2026-09-19" });
    await client.scores("EURUSD", { formula: "v1", from: "2026-06-01", to: "2026-09-19" });
    await client.report("EURUSD", { date: "2026-09-19" });
    await client.headlines("EURUSD", { date: "2026-09-19" });
    await client.events({ from: "2026-09-19", to: "2026-10-19", min_importance: 3 });
    await client.forecasts("EURUSD", { as_of: "2026-09-19", min_confidence: 0.5 });
    await client.spot("EURUSD", { from: "2026-06-01", to: "2026-09-19" });
    await client.chain("BTCUSD", { from: "2026-06-01" });
    await client.macroForecasts({ economy: "united_states", metric: "policy_rate" });
    await client.formulas();
    await client.health();
    expect(fetchFake.calls).toEqual([
      "http://x/api/v1/assets",
      "http://x/api/v1/overview?as_of=2026-09-19",
      "http://x/api/v1/assets/EURUSD/scores?formula=v1&from=2026-06-01&to=2026-09-19",
      "http://x/api/v1/assets/EURUSD/report?date=2026-09-19",
      "http://x/api/v1/assets/EURUSD/headlines?date=2026-09-19",
      "http://x/api/v1/events?from=2026-09-19&to=2026-10-19&min_importance=3",
      "http://x/api/v1/assets/EURUSD/forecasts?as_of=2026-09-19&min_confidence=0.5",
      "http://x/api/v1/assets/EURUSD/spot?from=2026-06-01&to=2026-09-19",
      "http://x/api/v1/assets/BTCUSD/chain?from=2026-06-01",
      "http://x/api/v1/macro/forecasts?economy=united_states&metric=policy_rate",
      "http://x/api/v1/formulas",
      "http://x/health",
    ]);
  });

  test("a route answers with the parsed body", async () => {
    const fetchFake = fakeFetch([{ status: 200, body: { status: "ok", last_run: "2026-09-18" } }]);
    const client = createClient({ fetch: fetchFake, baseUrl: () => "http://x" });
    expect(await client.health()).toEqual({ status: "ok", last_run: "2026-09-18" });
  });

  test("an error answer throws ApiError with the status and the detail", async () => {
    const fetchFake = fakeFetch([{ status: 404, body: { detail: "unknown asset XXXUSD" } }]);
    const client = createClient({ fetch: fetchFake, baseUrl: () => "http://x" });
    const failure = await client.scores("XXXUSD").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(404);
    expect((failure as ApiError).message).toBe("unknown asset XXXUSD");
  });

  test("a network failure becomes an ApiError without a status", async () => {
    const failingFetch = async () => {
      throw new TypeError("Failed to fetch");
    };
    const client = createClient({ fetch: failingFetch, baseUrl: () => "http://x" });
    const failure = await client.health().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBeNull();
    expect((failure as ApiError).message).toBe("cannot reach http://x/health (Failed to fetch)");
  });
});
