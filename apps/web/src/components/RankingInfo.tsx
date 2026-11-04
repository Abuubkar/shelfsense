import Link from "next/link";
import type { SearchItem } from "@/lib/api";
import { formatScore, ranksAt, share, stagesFor, tiesAt } from "@/lib/ranking";

// After Algolia's Ranking Info: the stages in pipeline order, the one that set the order marked, and the results
// either side of the product with the score that put it between them.

type Props = {
  item: SearchItem; items: SearchItem[]; weights: [number, number]; headSize: number; hrefFor: (id: string) => string;
};

export function RankingInfo({ item, items, weights, headSize, hrefFor }: Props) {
  const head = item.debug?.stage === "head";
  const stages = stagesFor(item);
  const decider = stages.at(-1)!;
  const scores = item.debug?.scores ?? {};
  const pct = (w: number) => `${Math.round(w * 100)}%`;
  // Model names keep their hyphens on one line ("ms-marco-MiniLM-L-6-v2" never wraps after "ms-").
  const about = (key: string, text: string) =>
    key === "hybrid" ? `${pct(weights[0])} keyword, ${pct(weights[1])} meaning` : text.replaceAll("-", "‑");
  const byRank = new Map(items.map((i) => [i.rank, i]));
  const around = [byRank.get(item.rank - 1), item, byRank.get(item.rank + 1)].filter((i): i is SearchItem => i != null);

  return (
    <div className="ranking">
      <p className="lead">
        <strong>#{item.rank} in these results.</strong>{" "}
        {head ? `The reranker set its place among the top ${headSize}.`
          : `Below the top ${headSize}, the combined keyword and meaning score sets the order; the reranker doesn’t run.`}
      </p>

      <table className="stages">
        <thead>
          <tr><th scope="col">Stage</th><th scope="col" className="value">Score</th><td className="bar" aria-hidden="true" /><th scope="col" className="rank">Rank <span className="of">of {items.length}</span></th></tr>
        </thead>
        <tbody>
          {stages.map((s) => {
            const rank = ranksAt(items, s.key).get(item.id), ties = tiesAt(items, item, s.key);
            return (
              <tr key={s.key} className={s === decider ? "decider" : undefined}>
                <th scope="row">
                  <span className="name">{s.label}{s === decider && <span className="tag">Sets the order</span>}</span>
                  <span className="about">{about(s.key, s.about)}</span>
                </th>
                <td className="value">{scores[s.key] != null ? formatScore(scores[s.key]) : "–"}</td>
                <td className="bar" aria-hidden="true"><span className="meter"><i style={{ width: `${Math.round(share(item, s, items) * 100)}%` }} /></span></td>
                <td className="rank">
                  {rank ? <>#{rank}{ties > 0 && <span className="about">tied with {ties}</span>}</> : <span className="about">no score</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {around.length > 1 && (
        <section className="around" aria-labelledby="around">
          <h3 id="around">Next to it, by {decider.label.toLowerCase()} score</h3>
          <ol>
            {around.map((i) => (
              <li key={i.id} className={i === item ? "self" : undefined} aria-current={i === item ? "true" : undefined}>
                <span className="pos">#{i.rank}</span>
                {i === item ? <span className="title">This product</span>
                  : <Link className="title" href={hrefFor(i.id)}>{i.title}</Link>}
                <span className="value">{i.debug?.scores?.[decider.key] != null ? formatScore(i.debug.scores[decider.key]) : "–"}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <p className="footnote">
        {head ? "Bars put each score on its stage’s own 0–1 scale. Keyword and meaning are rescaled so the lowest result scores 0."
          : "Bars show where it ranks at each stage among these results."}
      </p>
    </div>
  );
}
