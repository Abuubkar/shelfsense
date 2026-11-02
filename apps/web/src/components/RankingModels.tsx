import type { SearchItem } from "@/lib/api";

// Each ranking stage, and how to read its score. Kept from prototype C at the user's request (slice 5b).
const MODELS = [
  { key: "bm25", norm: "bm25_normalized", label: "Keyword match", how: "BM25 on title, brand, category and description" },
  { key: "knn", norm: "knn_normalized", label: "Meaning match", how: "bge-small embeddings, k-NN" },
  { key: "hybrid", norm: "hybrid", label: "Hybrid", how: "the two above, min-max normalized, weighted 50/50" },
  { key: "rerank", norm: null, label: "Reranker", how: "bge-reranker-base reads the query and product together" },
  { key: "tail", norm: null, label: "Combined score", how: "BM25 + k-NN, which orders results below the top 50" },
] as const;

/** How every ranking model scored the product, each on its own scale, and where it would rank by that model
 * alone among the results around it. The row that decided its position is highlighted. */
export function RankingModels({ item, items }: { item: SearchItem; items: SearchItem[] }) {
  const scores = item.debug?.scores ?? {};
  const rows = MODELS.filter((m) => scores[m.key] != null);
  const rankBy = (key: string) => {
    const scored = items.filter((i) => i.debug?.scores?.[key] != null)
      .sort((a, b) => (b.debug!.scores[key] ?? 0) - (a.debug!.scores[key] ?? 0));
    return { rank: scored.findIndex((i) => i.id === item.id) + 1, of: scored.length };
  };
  const bar = (key: string, norm: string | null) => {
    if (norm && scores[norm] != null) return scores[norm];
    if (key === "rerank") return 1 / (1 + Math.exp(-scores.rerank)); // a logit: through a sigmoid
    const { rank, of } = rankBy(key);
    return of ? 1 - (rank - 1) / of : 0;
  };
  const head = item.debug?.stage === "head";
  return (
    <>
      <p>Shown at #{item.rank}: {head ? "one of the top 50 by the hybrid score, then put in order by the reranker."
        : "below the top 50, ordered by the combined score (not reranked)."}</p>
      <table className="models">
        <thead><tr><th>Model</th><th className="num">Score</th><th>Relative</th><th className="num">Rank by this model</th></tr></thead>
        <tbody>
          {rows.map((m) => {
            const { rank, of } = rankBy(m.key);
            const decided = (m.key === "rerank" && head) || (m.key === "tail" && !head);
            return (
              <tr key={m.key} className={decided ? "decided" : undefined}>
                <td><b>{m.label}</b><span className="how">{m.how}</span></td>
                <td className="num">{scores[m.key].toFixed(3)}</td>
                <td className="bar"><i style={{ width: `${Math.round(Math.max(0, Math.min(1, bar(m.key, m.norm))) * 100)}%` }} /></td>
                <td className="num">#{rank} of {of}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted" style={{ fontSize: 12 }}>Each bar uses its model’s own scale. Ranks are among the {items.length} results
        around this one.</p>
    </>
  );
}
