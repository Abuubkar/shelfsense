# PROTOTYPE: search UI concepts (slice 5b). Throwaway.

Nine structurally different storefront search UIs on one page, switchable with `?variant=A`…`I`, the floating
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
| E. Instant search + toolbar | Does search-as-you-type (federated suggestions + previews) with a horizontal filter toolbar beat a sidebar? |
| F. Summary + compare | Does a synthesized "what we found" card and a top-3 comparison help, or get in the way? |
| G. Attribute-first | Do shoppers filter by colour, price, size, gender before reading results? |
| H. Mobile + filter tray | Does the design hold up on a phone (bottom-sheet tray, live result count)? |
| I. Composite | A's sidebar + B's editable chips + C's explanation drawer + D's suggestions: the one to build? |

Inspiration (patterns, not designs): Baymard on applied filters and filter UI
(https://baymard.com/blog/how-to-design-applied-filters, https://baymard.com/blog/ecommerce-filter-ui), Algolia's
federated autocomplete (https://www.algolia.com/doc/guides/solutions/ecommerce/autocomplete/tutorials/federated-search/),
NN/g on mobile faceted search (https://www.nngroup.com/articles/mobile-faceted-search/), and the AI shopping modes
(Google AI Mode comparisons, Amazon's Rufus, now Alexa for Shopping).
