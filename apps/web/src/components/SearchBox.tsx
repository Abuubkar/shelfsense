"use client";
import { useState } from "react";

/** The parent keys it by the searched text, so a new search (or Back) starts it afresh from `value`. */
export function SearchBox({ value, onSearch }: { value: string; onSearch: (q: string) => void }) {
  const [text, setText] = useState(value);
  return (
    <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); onSearch(text.trim()); }}>
      <label htmlFor="q" className="visually-hidden">Search products</label>
      <input id="q" type="search" value={text} placeholder="Search products, e.g. waterproof women's boots under $120"
             onChange={(e) => setText(e.target.value)} />
      <button type="submit">Search</button>
    </form>
  );
}
