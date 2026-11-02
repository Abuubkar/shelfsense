"use client";
// PROTOTYPE: cycles the ranking-section designs (?viz=...) on the product page. Dev builds only. Throwaway.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

const VIZ = [["journey", "Rank journey (bump chart)"], ["info", "Ranking info (Algolia-style)"],
  ["tiles", "Stat tiles + contribution"], ["bars", "Current bars"]] as const;

export function VizSwitcher({ current }: { current: string }) {
  const router = useRouter(), pathname = usePathname(), params = useSearchParams();
  const at = Math.max(0, VIZ.findIndex(([k]) => k === current));
  const go = (step: number) => {
    const next = new URLSearchParams(params.toString());
    next.set("viz", VIZ[(at + step + VIZ.length) % VIZ.length][0]);
    router.replace(`${pathname}?${next}`, { scroll: false });
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea")) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });
  return (
    <div className="viz-switcher" role="group" aria-label="Prototype: ranking view">
      <span className="tag">PROTOTYPE</span>
      <button onClick={() => go(-1)} aria-label="Previous design">←</button>
      <span>{at + 1}/{VIZ.length} · {VIZ[at][1]}</span>
      <button onClick={() => go(1)} aria-label="Next design">→</button>
    </div>
  );
}
