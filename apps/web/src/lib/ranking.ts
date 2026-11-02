// How a product placed at each ranking stage, for the product page's ranking views.
import type { SearchItem } from "./api";

export type Stage = { key: string; norm: string | null; label: string; model: string };

// Top 50 (the "head"): keyword and meaning retrieve, the hybrid blends them, the reranker sets the order.
export const HEAD_STAGES: Stage[] = [
  { key: "bm25", norm: "bm25_normalized", label: "Keyword", model: "BM25" },
  { key: "knn", norm: "knn_normalized", label: "Meaning", model: "bge-small k-NN" },
  { key: "hybrid", norm: "hybrid", label: "Hybrid", model: "50/50 blend" },
  { key: "rerank", norm: null, label: "Reranker", model: "bge-reranker-base" },
];
// Below the top 50 (the "tail"): ordered by the plain sum of the two retrieval scores.
export const TAIL_STAGES: Stage[] = [
  { key: "bm25", norm: null, label: "Keyword", model: "BM25" },
  { key: "knn", norm: null, label: "Meaning", model: "bge-small k-NN" },
  { key: "tail", norm: null, label: "Combined", model: "BM25 + k-NN" },
];

export const stagesFor = (item: SearchItem) => (item.debug?.stage === "head" ? HEAD_STAGES : TAIL_STAGES);

/** Rank of every item at one stage among the items that have that stage's score (1 = best); missing = no score.
 * Equal scores share the best rank (1, 2, 2, 4): BM25 often ties dozens of near-identical titles, and an
 * ordinal rank would invent an order the model never gave. */
export function ranksAt(items: SearchItem[], key: string): Map<string, number> {
  const scored = items.filter((i) => i.debug?.scores?.[key] != null)
    .sort((a, b) => b.debug!.scores[key] - a.debug!.scores[key]);
  const ranks = new Map<string, number>();
  scored.forEach((i, n) => {
    const prev = scored[n - 1];
    ranks.set(i.id, prev && prev.debug!.scores[key] === i.debug!.scores[key] ? ranks.get(prev.id)! : n + 1);
  });
  return ranks;
}

/** How many other items share this item's score at a stage. */
export function tiesAt(items: SearchItem[], item: SearchItem, key: string): number {
  const mine = item.debug?.scores?.[key];
  return mine == null ? 0 : items.filter((i) => i.id !== item.id && i.debug?.scores?.[key] === mine).length;
}

/** A 0..1 reading of a stage's score: the normalized score where the API gives one, a sigmoid for the reranker's
 * logit, else the rank's position among the scored items. */
export function share(item: SearchItem, stage: Stage, items: SearchItem[]): number {
  const s = item.debug?.scores ?? {};
  if (stage.norm && s[stage.norm] != null) return clamp(s[stage.norm]);
  if (stage.key === "rerank" && s.rerank != null) return 1 / (1 + Math.exp(-s.rerank));
  const ranks = ranksAt(items, stage.key), r = ranks.get(item.id);
  return r ? clamp(1 - (r - 1) / Math.max(1, ranks.size)) : 0;
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));
