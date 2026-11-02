import type { SearchItem } from "@/lib/api";
import { ranksAt, stagesFor, tiesAt } from "@/lib/ranking";

/** The numbers behind every ranking view, as a table (the accessible twin of the chart). */
export function RankTable({ item, items }: { item: SearchItem; items: SearchItem[] }) {
  const scores = item.debug?.scores ?? {};
  return (
    <details className="rank-table">
      <summary>Show the numbers</summary>
      <table>
        <thead><tr><th>Stage</th><th>Model</th><th className="num">Score</th><th className="num">Rank</th></tr></thead>
        <tbody>
          {stagesFor(item).map((s) => {
            const ranks = ranksAt(items, s.key);
            return (
              <tr key={s.key}><td>{s.label}</td><td>{s.model}</td>
                <td className="num">{scores[s.key]?.toFixed(3) ?? "–"}</td>
                <td className="num">{ranks.get(item.id) ? `#${ranks.get(item.id)} of ${ranks.size}${tiesAt(items, item, s.key) ? `, tied with ${tiesAt(items, item, s.key)}` : ""}` : "–"}</td></tr>
            );
          })}
        </tbody>
      </table>
    </details>
  );
}
