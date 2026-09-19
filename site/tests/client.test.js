import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ApiError,
  DEFAULT_API_URL,
  apiUrl,
  buildUrl,
  createClient,
  setApiUrl,
} from "../client.js";

class FakeStorage {
  constructor() {
    this.values = new Map();
  }
  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }
  setItem(key, value) {
    this.values.set(key, String(value));
  }
  removeItem(key) {
    this.values.delete(key);
  }
}

function fakeFetch(responses) {
  const calls = [];
  const fetchFake = async (url) => {
    calls.push(url);
    const answer = responses[calls.length - 1] ?? { status: 200, body: {} };
    return {
      ok: answer.status < 300,
      status: answer.status,
      json: async () => answer.body,
    };
  };
  fetchFake.calls = calls;
  return fetchFake;
}

test("the API URL defaults to localhost and the override survives in storage", () => {
  const storage = new FakeStorage();
  assert.equal(apiUrl(storage), DEFAULT_API_URL);
  setApiUrl("https://manc.example.org/", storage);
  assert.equal(apiUrl(storage), "https://manc.example.org"); // trailing slash dropped
  setApiUrl("   ", storage);
  assert.equal(apiUrl(storage), DEFAULT_API_URL); // blank resets
});

test("buildUrl encodes the params and drops the empty ones", () => {
  const url = buildUrl("http://localhost:8000", "/api/v1/events", {
    from: "2026-09-19",
    to: undefined,
    min_importance: 2,
    economy: null,
    metric: "",
  });
  assert.equal(url, "http://localhost:8000/api/v1/events?from=2026-09-19&min_importance=2");
  assert.equal(buildUrl("http://x", "/health", {}), "http://x/health");
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
  await client.macroForecasts({ economy: "united_states", metric: "policy_rate" });
  await client.formulas();
  await client.health();
  assert.deepEqual(fetchFake.calls, [
    "http://x/api/v1/assets",
    "http://x/api/v1/overview?as_of=2026-09-19",
    "http://x/api/v1/assets/EURUSD/scores?formula=v1&from=2026-06-01&to=2026-09-19",
    "http://x/api/v1/assets/EURUSD/report?date=2026-09-19",
    "http://x/api/v1/assets/EURUSD/headlines?date=2026-09-19",
    "http://x/api/v1/events?from=2026-09-19&to=2026-10-19&min_importance=3",
    "http://x/api/v1/assets/EURUSD/forecasts?as_of=2026-09-19&min_confidence=0.5",
    "http://x/api/v1/assets/EURUSD/spot?from=2026-06-01&to=2026-09-19",
    "http://x/api/v1/macro/forecasts?economy=united_states&metric=policy_rate",
    "http://x/api/v1/formulas",
    "http://x/health",
  ]);
});

test("a route answers with the parsed body", async () => {
  const fetchFake = fakeFetch([{ status: 200, body: { status: "ok", last_run: "2026-09-18" } }]);
  const client = createClient({ fetch: fetchFake, baseUrl: () => "http://x" });
  assert.deepEqual(await client.health(), { status: "ok", last_run: "2026-09-18" });
});

test("an error answer throws ApiError with the status and the detail", async () => {
  const fetchFake = fakeFetch([{ status: 404, body: { detail: "unknown asset XXXUSD" } }]);
  const client = createClient({ fetch: fetchFake, baseUrl: () => "http://x" });
  await assert.rejects(client.scores("XXXUSD", {}), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 404);
    assert.equal(error.message, "unknown asset XXXUSD");
    return true;
  });
});

test("a network failure becomes an ApiError without a status", async () => {
  const failingFetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  const client = createClient({ fetch: failingFetch, baseUrl: () => "http://x" });
  await assert.rejects(client.health(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, null);
    assert.match(error.message, /http:\/\/x/);
    return true;
  });
});
