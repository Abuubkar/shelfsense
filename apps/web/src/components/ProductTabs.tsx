"use client";
import { useState, type ReactNode } from "react";

/** Description / Specifications / Evidence, as accessible tabs (arrow keys move between them). */
export function ProductTabs({ tabs }: { tabs: { title: string; content: ReactNode }[] }) {
  const [current, setCurrent] = useState(0);
  return (
    <div className="tabs">
      <div role="tablist" aria-label="Product information"
           onKeyDown={(e) => {
             if (e.key === "ArrowRight") setCurrent((current + 1) % tabs.length);
             if (e.key === "ArrowLeft") setCurrent((current - 1 + tabs.length) % tabs.length);
           }}>
        {tabs.map((t, n) => (
          <button key={t.title} role="tab" id={`tab-${n}`} aria-selected={n === current} aria-controls={`panel-${n}`}
                  tabIndex={n === current ? 0 : -1} onClick={() => setCurrent(n)}>{t.title}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`}>{tabs[current].content}</div>
    </div>
  );
}
