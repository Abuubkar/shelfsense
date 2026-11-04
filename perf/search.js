// Search performance smoke (CI's perf-smoke job; `make perf-smoke` locally): 500 searches through the API's REST
// endpoint, drawn 60/30/10 from the golden head, torso and tail queries so popular ones repeat and later hit the
// parse cache. Latency is recorded per parse path (query_parse.source: rules, cache, llm, degraded); the gate is
// the fast path's p95 (rules, no model call) at 150 ms, from the slice plan. CI has no Ollama, so a query that
// needs the model degrades to keywords after a refused connection.
//
//   k6 run -e BASE_URL=http://localhost:8020 perf/search.js

import http from "k6/http";
import { check } from "k6";
import exec from "k6/execution";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8020";
const SEARCHES = 500;

const searchMs = new Trend("search_ms", true);

// The query log: fixed, so every run sends the same searches in the same order (Park-Miller, exact in a double).
const queries = open("../evals/golden/queries.jsonl").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
const byTier = { head: [], torso: [], tail: [] };
for (const q of queries) byTier[q.tier].push(q.q);
let seed = 7;
const next = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const log = [];
for (let i = 0; i < SEARCHES; i++) {
  const r = next();
  const tier = r < 0.6 ? "head" : r < 0.9 ? "torso" : "tail";
  log.push(byTier[tier][Math.floor(next() * byTier[tier].length)]);
}

export const options = {
  scenarios: { searches: { executor: "shared-iterations", vus: 4, iterations: SEARCHES, maxDuration: "15m" } },
  thresholds: {
    "search_ms{source:rules}": ["p(95)<150"],
    http_req_failed: ["rate<0.01"],
  },
  // Every path shows in the summary, gated or not.
  summaryTrendStats: ["count", "med", "p(95)", "max"],
};

export function setup() {
  // Load the embedding and reranker models before timing anything (the first search downloads and loads them).
  const res = http.get(`${BASE_URL}/v1/search?q=${encodeURIComponent("warm up")}`, { timeout: "300s" });
  check(res, { "warm-up search answered": (r) => r.status === 200 });
}

export default function () {
  const q = log[exec.scenario.iterationInTest % SEARCHES];
  const res = http.get(`${BASE_URL}/v1/search?q=${encodeURIComponent(q)}&page_size=24`, { tags: { name: "search" } });
  const ok = check(res, { "status is 200": (r) => r.status === 200 });
  if (!ok) return;
  const source = res.json("query_parse.source") || "none";
  searchMs.add(res.timings.duration, { source });
}
