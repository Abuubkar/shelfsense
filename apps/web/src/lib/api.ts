// The typed REST client (openapi-fetch over types generated from contracts/openapi.yaml: `pnpm codegen`).
import createClient from "openapi-fetch";
import type { components, paths } from "./api-types";

// In the browser, same-origin /api (forwarded by next.config.ts); on the server, the API itself. Absolute either way:
// fetch outside a browser (tests, server rendering) can't resolve a relative URL.
export const API_URL = process.env.SHELFSENSE_API ?? "http://localhost:8020";
const baseUrl = typeof window === "undefined" ? API_URL : `${window.location.origin}/api`;

// fetch is looked up per call, not captured once at import, so anything that wraps it later (MSW in tests) applies.
export const api = createClient<paths>({ baseUrl, fetch: (request) => globalThis.fetch(request) });

export type SearchResponse = components["schemas"]["SearchResponse"];
export type SearchItem = components["schemas"]["SearchItem"];
export type Facet = components["schemas"]["Facet"];
export type QueryParse = components["schemas"]["QueryParse"];
