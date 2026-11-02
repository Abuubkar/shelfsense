# PROTOTYPE: search UI concepts (slice 5b). Throwaway.

Four structurally different storefront search UIs on one page, switchable with `?variant=A|B|C|D`, the floating
bar at the bottom, or the ← → keys. They all read the real API (proxied, so no CORS setup). Pick one, or the
parts you like from several; the winner is rebuilt properly in `apps/web` (Next.js). This folder then moves to a
throwaway branch.

    uv run python apps/web_prototype/serve.py     # http://localhost:8040/?variant=A  (API must run on :8020)

| Variant | Question it answers |
|---|---|
| A. Classic storefront | Is a familiar facet sidebar + grid enough, with the parse shown as checked facets? |
| B. Editable query chips | Does showing what we understood (and letting you edit it) beat facets? |
| C. Explain the result | Do shoppers want evidence and scores beside results, not hidden in a debug view? |
| D. Guided refine | Is a conversation of suggested refinements better than browsing facets? |
