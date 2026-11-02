---
status: accepted
date: 2026-11-02
---

# Storefront look: "Ledger" (no colour in the chrome), drawn products, Geist

**Why.** The storefront read as a generic kit: system font on off-white, white cards, a blue button, flat colour
blocks where products should be, and nothing only Shelfsense has. That is the first "tell" taste-skill's app-screen
guide lists (github.com/Leonxlnx/taste-skill, `references/app-screens.md`, distilled from 23 measured product
screens). Its rules were read and applied by hand; its scripts were not run.

**How it was chosen.** Three looks were built on the real storefront behind a dev-only switcher (branch
`prototype/storefront-taste`), each in light and dark, at desktop and phone width:

| Look | Move | Verdict |
|---|---|---|
| A. Ledger | No colour in the chrome: near-black ink and primary, Geist, tight 8px corners; the products' own colours are the only hue on screen | **Chosen** |
| B. Field guide | A pine-tinted frame around a white sheet, IBM Plex, stone product tiles, pine on the AI parts | Not chosen |
| C. Outfitter | Trail orange on small marks, pale tints, soft 16px corners and pill controls, DM Sans | Not chosen |

**Built, in every look and now in `apps/web`:**

- **Drawn products** (`ProductArt`): with no photographs, a product is drawn as its kind (18 kinds read from the
  title, then the category) filled with its base colour, and the product page says it's a drawing. Never a fake
  product shot; the empty thumbnail strip is gone.
- **Why it matched**: the search's words are marked in each title by stem (`lib/highlight.ts`); a result with none
  of them is labelled "Related" (found by meaning). Honest from the title alone, so the search page needs no
  `debug=true`.
- **"Read from your search"** chips sit in the results heading, where they read as the product's own feature.
- Sentence-case headings (no tracked uppercase), a shelf mark beside the wordmark, a two-column grid on phones,
  tabular figures, one typeface.
- **Geist through `next/font/google`**: fetched at build time and served from this app, so the browser never calls
  Google and there is no new npm package.

## Alternatives

- **Field guide (B)** gave the most "outdoor catalog" identity but frames every screen in colour; the catalog spans
  kitchenware and electronics too.
- **Outfitter (C)** was the warmest, but colour on matched words and controls competes with the products' colours.
- **"Keyword vs meaning" match badges** from the debug scores: nearly every result matches on both, so the badge said
  the same thing on every card.

## Assumptions

- Real product photos will replace the drawings; `ProductArt` is the one place to swap.
- A product kind outside the 18 falls back to a plain tag shape; add a kind when the catalog grows one.
