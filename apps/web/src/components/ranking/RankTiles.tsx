import type { SearchItem } from "@/lib/api";
import { ranksAt, share, stagesFor, tiesAt } from "@/lib/ranking";
import { RankTable } from "./RankTable";

// PROTOTYPE variant "tiles": a row of stat tiles (the rank is the number that matters at each stage), then how the
// hybrid score was put together from its two parts, as SHAP-style contribution views show a score's make-up.

export function RankTiles({ item, items, weights }: { item: SearchItem; items: SearchItem[]; weights: [number, number] }) {
  const stages = stagesFor(item);
  const scores = item.debug?.scores ?? {};
  const decider = stages.at(-1)!;
  const keyword = (scores.bm25_normalized ?? 0) * weights[0], meaning = (scores.knn_normalized ?? 0) * weights[1];
  return (
    <figure className="tiles">
      <figcaption><strong>#{item.rank} in the results.</strong> Its rank at each stage:</figcaption>
      <div className="tile-row">
        {stages.map((s) => {
          const ranks = ranksAt(items, s.key), rank = ranks.get(item.id);
          const pct = Math.round(share(item, s, items) * 100);
          return (
            <div key={s.key} className={`tile${s === decider ? " decider" : ""}`}>
              <span className="label">{s.label}{s === decider && <em> · decided</em>}</span>
              <span className="big">{rank ? `#${rank}` : "–"}</span>
              <span className="of">{rank ? `of ${ranks.size}` : "no score"}{tiesAt(items, item, s.key) ? `, tied with ${tiesAt(items, item, s.key)}` : ""} · {s.model}</span>
              <span className="meter" aria-hidden="true"><i style={{ width: `${pct}%` }} /></span>
            </div>
          );
        })}
      </div>
      {scores.hybrid != null && (
        <div className="contribution">
          <p>How the hybrid score <b>{scores.hybrid.toFixed(3)}</b> was put together:</p>
          <div className="stack" role="img" aria-label={`Keyword contributes ${keyword.toFixed(2)}, meaning ${meaning.toFixed(2)}`}>
            <i className="k" style={{ width: `${keyword * 100}%` }} />
            <i className="m" style={{ width: `${meaning * 100}%` }} />
          </div>
          <div className="axis"><span>0</span><span>0.5</span><span>1</span></div>
          <p className="legend">
            <span className="key k" /> Keyword {weights[0]} × {(scores.bm25_normalized ?? 0).toFixed(2)} = {keyword.toFixed(2)}
            <span className="key m" /> Meaning {weights[1]} × {(scores.knn_normalized ?? 0).toFixed(2)} = {meaning.toFixed(2)}
          </p>
        </div>
      )}
      <RankTable item={item} items={items} />
    </figure>
  );
}
