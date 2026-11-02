import type { SearchItem } from "@/lib/api";

// Each ranking stage, and how to read its score. Kept from prototype C at the user's request (slice 5b).
const MODELS = [
  { key: "bm25", norm: "bm25_normalized", label: "Keyword match", how: "BM25 on title, brand, category, description" },
  { key: "knn", norm: "knn_normalized", label: "Meaning match", how: "bge-small embeddings, k-NN" },
  { key: "hybrid", norm: "hybrid", label: "Hybrid", how: "the two above, min-max normalized, 50/50" },
  { key: "rerank", norm: null, label: "Reranker", how: "bge-reranker-base reads query and product together" },
  { key: "tail", norm: null, label: "Combined score", how: "BM25 + k-NN, orders results below the top 50" },
] as const;

/** A bar chart of how every ranking model scored the product, each bar on that model's own 0–1 scale, with where
 * the product would rank by that model alone among the results around it. The bar that decided its position is
 * highlighted. */
export function RankingModels({ item, items }: { item: SearchItem; items: SearchItem[] }) {
  const scores = item.debug?.scores ?? {};
  const rows = MODELS.filter((m) => scores[m.key] != null);
  const rankBy = (key: string) => {
    const scored = items.filter((i) => i.debug?.scores?.[key] != null)
      .sort((a, b) => (b.debug!.scores[key] ?? 0) - (a.debug!.scores[key] ?? 0));
    return { rank: scored.findIndex((i) => i.id === item.id) + 1, of: scored.length };
  };
  // 0..1 for the bar. BM25 and k-NN use their normalized scores; the reranker's logit goes through a sigmoid; a
  // score with no natural scale (the tail's) is drawn by its rank instead.
  const share = (key: string, norm: string | null) => {
    if (norm && scores[norm] != null) return scores[norm];
    if (key === "rerank") return 1 / (1 + Math.exp(-scores.rerank));
    const { rank, of } = rankBy(key);
    return of ? 1 - (rank - 1) / of : 0;
  };
  const head = item.debug?.stage === "head";
  return (
    <figure className="chart" aria-label="Scores from each ranking model">
      <figcaption>Shown at <b>#{item.rank}</b>: {head ? "one of the top 50 by the hybrid score, then put in order by the reranker."
        : "below the top 50, ordered by the combined score (not reranked)."}</figcaption>
      <ul>
        {rows.map((m) => {
          const { rank, of } = rankBy(m.key);
          const decided = (m.key === "rerank" && head) || (m.key === "tail" && !head);
          const pct = Math.round(Math.max(0, Math.min(1, share(m.key, m.norm))) * 100);
          return (
            <li key={m.key} className={decided ? "decided" : undefined}>
              <span className="label"><b>{m.label}</b><small>{m.how}</small></span>
              <span className="track" role="img" aria-label={`${m.label}: ${pct}% of its scale, score ${scores[m.key].toFixed(3)}`}>
                <i style={{ width: `${pct}%` }} />
                <em>{scores[m.key].toFixed(3)}</em>
              </span>
              <span className="rank">#{rank}<small>of {of}</small></span>
            </li>
          );
        })}
      </ul>
      <p className="muted note">Each bar is on its model’s own scale (keyword and meaning after min-max normalization, the
        reranker through a sigmoid). “#” is where this product would rank by that model alone among the {items.length} results
        around it.{head ? " The highlighted bar decided the order." : ""}</p>
    </figure>
  );
}
