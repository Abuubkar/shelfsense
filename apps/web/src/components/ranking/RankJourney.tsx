import type { SearchItem } from "@/lib/api";
import { ranksAt, stagesFor } from "@/lib/ranking";
import { RankTable } from "./RankTable";

// PROTOTYPE variant "journey": a bump chart of the product's rank at each stage (Datawrapper's advice: when position
// matters more than value, plot ranks). This product is the one accent line; the next few results are grey context.
const W = 640, H = 280, TOP = 58, BOTTOM = 18, LEFT = 74, RIGHT = 74;

export function RankJourney({ item, items }: { item: SearchItem; items: SearchItem[] }) {
  const stages = stagesFor(item);
  const ranks = stages.map((s) => ranksAt(items, s.key));
  const context = items.filter((i) => i.id !== item.id).sort((a, b) => a.rank - b.rank).slice(0, 6);
  // Deep enough for every line drawn: the context results can rank far lower than this product at some stages.
  const deepest = Math.max(5, ...[item, ...context].flatMap((i) => ranks.map((r) => r.get(i.id) ?? 0)));
  const x = (n: number) => LEFT + (n * (W - LEFT - RIGHT)) / (stages.length - 1);
  const y = (rank: number) => TOP + ((rank - 1) * (H - TOP - BOTTOM)) / (deepest - 1);
  const path = (id: string) => {
    let d = "", pen = false;
    ranks.forEach((r, n) => {
      const rank = r.get(id);
      if (rank == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(n).toFixed(1)},${y(rank).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const mine = ranks.map((r) => r.get(item.id));
  const final = mine.at(-1);
  const sentence = stages.slice(0, -1).map((s, n) => `${s.label.toLowerCase()} #${mine[n] ?? "–"}`).join(", ");
  const ticks = [...new Set([1, ...[10, 25].filter((t) => t < deepest - 3), deepest])];

  return (
    <figure className="journey">
      <figcaption>
        <strong>#{item.rank} in the results.</strong> By {sentence}; the {stages.at(-1)!.label.toLowerCase()} {final != null && mine.at(-2) != null && final < mine.at(-2)! ? "moved it up" : final === mine.at(-2) ? "kept it" : "placed it"} to #{final ?? item.rank}.
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="journey-desc">
        <desc id="journey-desc">Rank of this product at each ranking stage: {stages.map((s, n) => `${s.label} ${mine[n] ?? "no score"}`).join(", ")}.</desc>
        {ticks.map((t) => (
          <g key={t} className="grid">
            <line x1={LEFT - 8} x2={W - RIGHT + 8} y1={y(t)} y2={y(t)} />
            <text x={LEFT - 14} y={y(t) + 4} textAnchor="end">#{t}</text>
          </g>
        ))}
        {stages.map((s, n) => (
          <g key={s.key} className="stage">
            <text x={x(n)} y={18} textAnchor="middle" className="name">{s.label}</text>
            <text x={x(n)} y={34} textAnchor="middle" className="model">{s.model}</text>
          </g>
        ))}
        {context.map((c) => <path key={c.id} d={path(c.id)} className="context"><title>{`#${c.rank} ${c.title}`}</title></path>)}
        <path d={path(item.id)} className="mine" />
        {mine.map((rank, n) => rank == null ? null : (
          <g key={n} className="point">
            <circle cx={x(n)} cy={y(rank)} r={6}><title>{`${stages[n].label}: #${rank}`}</title></circle>
            <text x={x(n)} y={y(rank) - 11} textAnchor="middle">#{rank}</text>
          </g>
        ))}
      </svg>
      <p className="legend"><span className="key mine-key" /> This product <span className="key context-key" /> The next results, for comparison</p>
      <RankTable item={item} items={items} />
    </figure>
  );
}
