import type { SearchItem } from "@/lib/api";
import { ranksAt, share, stagesFor, tiesAt } from "@/lib/ranking";
import { RankTable } from "./RankTable";

// PROTOTYPE variant "info": Algolia's Ranking Info, in pipeline order, text first with thin meters, and the
// comparison with the neighbouring results Algolia recommends ("why is it above the next one?").

export function RankingInfo({ item, items }: { item: SearchItem; items: SearchItem[] }) {
  const stages = stagesFor(item);
  const decider = stages.at(-1)!;
  const scores = item.debug?.scores ?? {};
  const byRank = new Map(items.map((i) => [i.rank, i]));
  const above = byRank.get(item.rank - 1), below = byRank.get(item.rank + 1);
  const compare = (other: SearchItem, word: "above" | "below") => {
    const mine = scores[decider.key], theirs = other.debug?.scores?.[decider.key];
    return (
      <li>
        <span className="muted">{word === "above" ? "Ranked below" : "Ranked above"} #{other.rank}</span>{" "}
        <span className="title">{other.title}</span>
        {mine != null && theirs != null && <span className="muted">: {decider.label.toLowerCase()} {mine.toFixed(2)} vs {theirs.toFixed(2)}</span>}
      </li>
    );
  };
  return (
    <figure className="info">
      <figcaption><strong>#{item.rank} in the results</strong>, decided by the {decider.label.toLowerCase()} ({decider.model}).</figcaption>
      <ol className="criteria">
        {stages.map((s) => {
          const ranks = ranksAt(items, s.key), rank = ranks.get(item.id);
          const pct = Math.round(share(item, s, items) * 100);
          return (
            <li key={s.key} className={s === decider ? "decider" : undefined}>
              <span className="what"><b>{s.label}</b><small>{s.model}</small></span>
              <span className="value">{scores[s.key]?.toFixed(3) ?? "–"}</span>
              <span className="meter" role="img" aria-label={`${s.label}: ${pct}% of its scale`}><i style={{ width: `${pct}%` }} /></span>
              <span className="rank">{rank ? <>#{rank} <small>of {ranks.size}{tiesAt(items, item, s.key) ? `, tied with ${tiesAt(items, item, s.key)}` : ""}</small></> : "–"}</span>
            </li>
          );
        })}
      </ol>
      <ul className="neighbours">{below && compare(below, "below")}{above && compare(above, "above")}</ul>
      <RankTable item={item} items={items} />
    </figure>
  );
}
