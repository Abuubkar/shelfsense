---
status: accepted
date: 2026-11-02
---

# Storefront UI: classic facet storefront with a separate product page, chosen from prototypes

**How it was chosen.** Nine throwaway search-UI concepts and five product-detail designs were built against the
real API and compared in the browser (branch `prototype/05b-search-ui`, `apps/web_prototype/`; its README lists
the question each answered). Patterns came from Baymard (applied filters, filter components), Algolia (federated
autocomplete), NN/g (mobile filter trays) and the AI shopping modes (summary and comparison).

| Concept | Verdict |
|---|---|
| A. Classic storefront (facet sidebar, card grid, load more, parse shown as "From your search") | **Chosen** |
| B. Editable query chips, C. Explain the result, D. Guided refine | Not chosen; C's ranking-model comparison kept on the product page |
| E. Instant search, F. Summary + compare, G. Attribute-first, H. Mobile tray, I. Composite | Not chosen |
| Detail 1–5: modal, full page, specs-first drawer, inline expand, master-detail | **Full product page** (2) with the specs-first sources (3) and C's model comparison |

**Built** (`apps/web`, Next.js 16 App Router, TypeScript 5.9):

- `/`: the search page. The URL is the state (q, facets, price bucket), so searches are shareable and Back works.
  REST through openapi-fetch with types generated from `contracts/openapi.yaml`. Load more follows the opaque
  cursor. Notices for a degraded parse and a relaxed price.
- `/products/[id]`: a server-rendered page. The product comes from GraphQL with codegen-typed documents (no client
  library: one query, no cache to manage). Facts name their source (the seller's data, or the listing's words with
  the quote). Evidence is highlighted by code-point offsets. When opened from a search, it re-reads that search's
  per-stage scores to show how each ranking model (BM25, k-NN, hybrid, reranker) placed it.
- The browser calls `/api/*` on its own origin; Next forwards to the API, so the API needs no CORS.
- Money is formatted by integer arithmetic identical to the API's (`money.py`), checked against shared fixtures.

## Alternatives

- **The composite (I)** packed every idea in; it tested well for features but the user preferred A's simplicity.
- **A drawer for details** keeps the grid in view, but a page gives room for specs, evidence and the ranking
  explanation, and has its own URL.
- **Apollo/urql for GraphQL**: worth it with many queries and a client cache; one server-side query isn't.

## Assumptions

- Product images will replace the colour swatches; the layout reserves the space.
- The ranking explanation re-runs the search (48 results) when a product is opened from it; fine at this scale,
  and the page still renders without it.
