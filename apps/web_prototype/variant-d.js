// PROTOTYPE variant D: guided refine. A conversation: each search or refinement is a turn; the system answers in a
// sentence, shows the best few results in a strip, and offers next steps built from the facets ("Only black · 5",
// "Under $25 · 3"). No sidebar, no grid. Question: is suggesting refinements better than browsing facets? Throwaway.
import { esc, money, parsedSummary, search } from "./api.js";

export const NAME = "Guided refine";

export function mount(root) {
  const turns = [];
  root.innerHTML = `
  <style>
    .d-wrap{max-width:900px;margin:0 auto;padding:24px 20px 140px}
    .d-turn{margin:18px 0}.d-you{display:flex;justify-content:flex-end}.d-you span{background:var(--ink);color:var(--bg);border-radius:16px 16px 4px 16px;padding:9px 14px;max-width:70%}
    .d-sys{background:var(--card);border:1px solid var(--line);border-radius:16px 16px 16px 4px;padding:14px 16px;margin-top:10px}
    .d-say{font-size:15px;line-height:1.5}.d-say .muted{font-size:13px}
    .d-strip{display:flex;gap:12px;overflow-x:auto;margin:12px 0 4px;padding-bottom:6px}
    .d-mini{min-width:180px;max-width:180px;border:1px solid var(--line);border-radius:10px;padding:10px;font-size:13px;display:flex;flex-direction:column;gap:6px;background:var(--bg)}
    .d-mini .price{margin-top:auto}
    .d-next{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .d-next button{border:1px solid var(--accent);color:var(--accent);background:transparent;border-radius:999px;padding:5px 12px;font-size:13px}
    .d-next button:hover{background:var(--accent-bg)}
    .d-ask{position:fixed;left:0;right:0;bottom:60px;display:flex;justify-content:center;padding:0 20px}
    .d-ask form{display:flex;gap:8px;width:100%;max-width:860px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px;box-shadow:0 4px 16px rgba(0,0,0,.08)}
    .d-ask input{flex:1;border:0;outline:0;padding:10px;background:transparent;color:var(--ink);font-size:15px}
    .d-ask button{border:0;border-radius:10px;padding:0 16px;background:var(--accent);color:#fff}
    .d-reset{border:0;background:transparent;color:var(--muted);text-decoration:underline;font-size:13px}
  </style>
  <div class="d-wrap"><div class="d-turns"></div></div>
  <div class="d-ask"><form><input aria-label="Ask" placeholder="What are you looking for? Try “kids rain boots green”"><button>Send</button></form></div>`;
  const $ = (s) => root.querySelector(s);
  $("form").onsubmit = (e) => { e.preventDefault(); const q = $("input").value.trim(); if (q) { $("input").value = ""; ask({ q, filters: {}, said: q }); } };

  async function ask(turn) {
    const body = await search({ q: turn.q, filters: turn.filters, pageSize: 8 });
    turns.push({ ...turn, body });
    render();
    scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
  function sentence(t) {
    const qp = t.body.query_parse, chips = parsedSummary(qp).filter((c) => !c.relaxed);
    const what = `${qp?.keywords || t.q}${chips.length ? ", " + chips.map((c) => c.label).join(", ") : ""}`;
    let s = t.body.total ? `I found <b>${t.body.total.toLocaleString()}</b> for <b>${esc(what)}</b>.` : `Nothing matched <b>${esc(what)}</b>.`;
    if (qp?.price_relaxed) s += ` <span class="muted">Nothing was in your price range, so I left the price out.</span>`;
    if (qp?.source === "degraded") s += ` <span class="muted">I couldn’t work out filters in time, so these match your exact words.</span>`;
    return s;
  }
  function suggestions(t) {
    const out = [], f = Object.fromEntries(t.body.facets.map((x) => [x.name, x.values]));
    for (const v of (f.color ?? []).slice(0, 3)) if (v.count < t.body.total) out.push({ label: `Only ${v.label} · ${v.count}`, filters: { color: [v.value] } });
    for (const v of (f.price ?? []).slice(0, 2)) if (v.count < t.body.total) {
      const [lo, hi] = v.value.split("-"); out.push({ label: `${v.label} · ${v.count}`, filters: { price_min: lo || undefined, price_max: hi ? Number(hi) - 1 : undefined } });
    }
    for (const v of (f.brand ?? []).slice(0, 2)) if (v.count < t.body.total) out.push({ label: `${v.label} only · ${v.count}`, filters: { brand: [v.value] } });
    return out;
  }
  function render() {
    $(".d-turns").innerHTML = turns.map((t, n) => `<div class="d-turn"><div class="d-you"><span>${esc(t.said)}</span></div>
      <div class="d-sys"><div class="d-say">${sentence(t)}</div>
      <div class="d-strip">${t.body.items.map((i) => `<div class="d-mini"><span>${esc(i.title)}</span><span class="muted">${[i.brand, i.color, i.size].filter(Boolean).map(esc).join(" · ")}</span><span class="price">${money(i.price)}</span></div>`).join("")}</div>
      ${n === turns.length - 1 ? `<div class="d-next">${suggestions(t).map((s, k) => `<button data-k="${k}">${esc(s.label)}</button>`).join("")}${turns.length > 1 ? `<button class="d-reset">Start over</button>` : ""}</div>` : ""}
      </div></div>`).join("");
    const last = turns[turns.length - 1], options = last ? suggestions(last) : [];
    root.querySelectorAll(".d-next button[data-k]").forEach((b) => b.onclick = () => {
      const s = options[Number(b.dataset.k)];
      ask({ q: last.q, filters: { ...last.filters, ...s.filters }, said: s.label.split(" · ")[0] });
    });
    root.querySelector(".d-reset")?.addEventListener("click", () => { turns.length = 0; render(); });
  }
  ask({ q: "waterproof women's hiking boots under $120", filters: {}, said: "waterproof women's hiking boots under $120" });
}
