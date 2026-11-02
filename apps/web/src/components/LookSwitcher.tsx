"use client";
import { useEffect, useState } from "react";

// PROTOTYPE (dev only): flips the storefront between the three looks and the current one. The choice is a cookie,
// so it follows you from the search page to a product page and survives a reload.
export const LOOKS = [
  { id: "current", label: "Current" },
  { id: "ledger", label: "A · Ledger" },
  { id: "field", label: "B · Field guide" },
  { id: "outfitter", label: "C · Outfitter" },
] as const;

export function LookSwitcher({ initial }: { initial: string }) {
  const [look, setLook] = useState(initial);
  useEffect(() => {
    document.cookie = `look=${look}; path=/; max-age=31536000; samesite=lax`;
    if (look === "current") delete document.documentElement.dataset.look;
    else document.documentElement.dataset.look = look;
  }, [look]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || !["[", "]"].includes(e.key)) return;
      const n = LOOKS.findIndex((l) => l.id === look);
      setLook(LOOKS[(n + (e.key === "]" ? 1 : LOOKS.length - 1)) % LOOKS.length].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [look]);
  return (
    <div className="look-switcher" role="group" aria-label="Prototype look">
      <b>LOOK</b>
      {LOOKS.map((l) => <button key={l.id} aria-pressed={look === l.id} onClick={() => setLook(l.id)}>{l.label}</button>)}
    </div>
  );
}
