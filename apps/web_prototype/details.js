// PROTOTYPE: five product-detail designs for variant A, chosen with ?detail=1..5. Each gets the clicked card and
// A's page, and lays itself out however it likes. Throwaway.
import { esc, money, product } from "./api.js";
import { SWATCH, breadcrumb, descriptionHtml, rawHtml, similar, specs, titleHtml } from "./detail-shared.js";

const close = (sel) => document.querySelectorAll(sel).forEach((el) => el.remove());
const img = (p, h) => `<div style="height:${h}px;border-radius:10px;background:${SWATCH[p.color_base ?? p.extracted_attributes.find((a) => a.name === "color")?.value] ?? "#b9b7ae"}"></div>`;
const conf = (p) => (p.category ? ` <span class="muted" title="Model confidence">(${Math.round(p.category.confidence * 100)}%)</span>` : "");
const specRow = (s) => `<tr><th>${esc(s.label)}</th><td>${esc(s.value)}${s.source === "listing" ? ` <span class="src" title="Read from the listing: “${esc(s.quote)}” (${s.field})">from listing</span>` : ""}</td></tr>`;
const STYLE = `<style>
  .dt-specs{width:100%;border-collapse:collapse;font-size:14px}.dt-specs th{text-align:left;color:var(--muted);font-weight:500;width:120px;padding:6px 0;vertical-align:top}.dt-specs td{padding:6px 0}
  .dt-specs tr{border-bottom:1px solid var(--line)}.src{font-size:11px;background:var(--accent-bg);color:var(--accent);border-radius:4px;padding:1px 5px;cursor:help}
  .dt-sim{display:flex;gap:10px;overflow-x:auto}.dt-sim div{min-width:150px;max-width:150px;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:12px;display:flex;flex-direction:column;gap:4px;background:var(--card)}
  .dt-btn{border:0;border-radius:10px;padding:11px 18px;background:var(--accent);color:#fff;font-size:15px}
  .dt-x{border:0;background:transparent;color:var(--muted);font-size:20px;cursor:pointer}
  .dt-crumb{font-size:12px;color:var(--muted)}
</style>`;
async function simHtml(p) {
  const items = await similar(p);
  return items.length ? `<div class="dt-sim">${items.map((i) => `<div><span>${esc(i.title)}</span><b class="price">${money(i.price)}</b></div>`).join("")}</div>` : `<p class="muted">Nothing similar indexed.</p>`;
}

// 1. Quick-view modal over the grid: the essentials, and a way to the full page.
const modal = {
  NAME: "Quick-view modal",
  async open({ item }) {
    close(".dt-layer");
    const p = await product(item.id);
    const el = document.createElement("div");
    el.className = "dt-layer";
    el.innerHTML = `${STYLE}<div style="position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:30;display:flex;align-items:center;justify-content:center" class="scrim">
      <div role="dialog" aria-label="${esc(p.title)}" style="background:var(--card);border-radius:16px;width:min(820px,94vw);max-height:88vh;overflow:auto;padding:22px;display:grid;grid-template-columns:300px 1fr;gap:24px;position:relative">
      <button class="dt-x" style="position:absolute;top:10px;right:14px" aria-label="Close">✕</button>
      <div>${img(p, 300)}</div><div><div class="dt-crumb">${breadcrumb(p)}${conf(p)}</div><h2 style="margin:6px 0">${titleHtml(p)}</h2>
      <div class="price" style="font-size:22px;margin:8px 0 14px">${money(p.price)}</div>
      <table class="dt-specs">${specs(p).slice(0, 5).map(specRow).join("")}</table>
      <p style="font-size:14px;line-height:1.6">${descriptionHtml(p, 260)}${(p.description ?? "").length > 260 ? "…" : ""}</p>
      <button class="dt-btn">View full details</button></div></div></div>`;
    el.querySelector(".scrim").onclick = (e) => { if (e.target.classList.contains("scrim")) el.remove(); };
    el.querySelector(".dt-x").onclick = () => el.remove();
    el.querySelector(".dt-btn").onclick = () => { el.remove(); page.open({ item, root: document.querySelector("#app") }); };
    document.body.append(el);
    addEventListener("keydown", function esc_(e) { if (e.key === "Escape") { el.remove(); removeEventListener("keydown", esc_); } });
  },
};

// 2. Full product page in place of the results, with tabs, similar products, and a way back to the same results.
const page = {
  NAME: "Full product page",
  async open({ item, root }) {
    const body = root.querySelector(".a-body"), scroll = scrollY;
    const p = await product(item.id);
    body.style.display = "none";  // not `hidden`: the page CSS sets display on .a-body
    close(".dt-page");
    const el = document.createElement("div");
    el.className = "dt-page";
    el.innerHTML = `${STYLE}<div style="max-width:1100px;margin:auto;padding:18px 24px 100px">
      <button class="back" style="border:0;background:transparent;color:var(--accent);padding:0">← Back to results</button>
      <div class="dt-crumb" style="margin:10px 0 16px">${breadcrumb(p)}${conf(p)}</div>
      <div style="display:grid;grid-template-columns:1.1fr 1fr;gap:36px">
        <div>${img(p, 420)}<div style="display:flex;gap:8px;margin-top:8px">${[1, 2, 3, 4].map(() => `<div style="flex:1;height:70px;border-radius:8px;background:var(--line)"></div>`).join("")}</div></div>
        <div><div class="muted">${esc(p.brand ?? "")}</div><h1 style="margin:4px 0 10px;font-size:26px">${titleHtml(p)}</h1>
        <div class="price" style="font-size:26px">${money(p.price)}</div><p class="muted" style="font-size:13px">Sold by ${esc(p.supplier)}</p>
        <table class="dt-specs" style="margin:14px 0">${specs(p).slice(0, 4).map(specRow).join("")}</table>
        <button class="dt-btn" style="width:100%">Add to cart</button></div></div>
      <div style="margin-top:34px"><div class="tabs" style="display:flex;gap:6px;border-bottom:1px solid var(--line)">${["Description", "Specifications", "Evidence"].map((t, n) => `<button data-t="${n}" style="border:0;background:transparent;color:var(--ink);padding:10px 14px;border-bottom:2px solid ${n ? "transparent" : "var(--accent)"}">${t}</button>`).join("")}</div>
        <div class="panel" style="padding:16px 0;font-size:15px;line-height:1.7"></div></div>
      <h3 style="margin-top:28px">Similar products</h3><div class="sim">Loading…</div></div>`;
    const panels = [
      `<p>${descriptionHtml(p)}</p>`,
      `<table class="dt-specs">${specs(p).map(specRow).join("")}</table>`,
      `<p class="muted" style="font-size:13px">Highlighted words are what the attributes were read from.</p><p><b>Title</b><br>${titleHtml(p)}</p><p><b>Description</b><br>${descriptionHtml(p)}</p><p><b>Supplier columns</b><br>${rawHtml(p)}</p>`,
    ];
    const show = (n) => { el.querySelector(".panel").innerHTML = panels[n]; el.querySelectorAll(".tabs button").forEach((b) => (b.style.borderBottomColor = Number(b.dataset.t) === n ? "var(--accent)" : "transparent")); };
    el.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => show(Number(b.dataset.t)));
    show(0);
    el.querySelector(".back").onclick = () => { el.remove(); body.style.display = ""; scrollTo(0, scroll); };
    root.append(el);
    scrollTo(0, 0);
    el.querySelector(".sim").innerHTML = await simHtml(p);
  },
};

// How each ranking model scored the product, each on its own scale, and where it would have ranked by that model
// alone among the loaded results (from prototype C's "why it ranked", which the user wanted kept).
const MODELS = [
  ["bm25", "bm25_normalized", "Keyword match", "BM25 on title, brand, category, description"],
  ["knn", "knn_normalized", "Meaning match", "bge-small embeddings, k-NN"],
  ["hybrid", "hybrid", "Hybrid", "the two above, min-max normalized, 50/50"],
  ["rerank", null, "Reranker", "bge-reranker-base reads query and product together"],
  ["tail", null, "Combined score", "BM25 + k-NN, used below the top 50"],
];
function modelsHtml(item, items) {
  const s = item.debug?.scores ?? {};
  const rows = MODELS.filter(([key]) => s[key] != null);
  if (!rows.length) return `<p class="muted" style="font-size:13px">No scores for this result (they come with the search's debug view).</p>`;
  const rankBy = (key) => {
    const scored = items.filter((i) => i.debug?.scores?.[key] != null).sort((a, b) => b.debug.scores[key] - a.debug.scores[key]);
    return [scored.findIndex((i) => i.id === item.id) + 1, scored.length];
  };
  const bar = (key, normKey) => {
    const v = normKey ? s[normKey] : key === "rerank" ? 1 / (1 + Math.exp(-s.rerank)) : null;
    if (v == null) { const [r, n] = rankBy(key); return n ? 1 - (r - 1) / n : 0; }
    return Math.max(0, Math.min(1, v));
  };
  const stage = item.debug.stage === "head"
    ? `Shown at #${item.rank}: one of the top 50 by the hybrid score, then put in order by the reranker.`
    : `Shown at #${item.rank}: below the top 50, ordered by the combined score (not reranked).`;
  return `<p style="font-size:13px;margin:0 0 8px">${stage}</p><table class="dt-models">${rows.map(([key, normKey, label, how]) => {
    const [r, n] = rankBy(key);
    const final = (key === "rerank" && item.debug.stage === "head") || (key === "tail" && item.debug.stage === "tail");
    return `<tr class="${final ? "final" : ""}"><td><b>${label}</b><div>${how}</div></td><td class="num">${s[key].toFixed(3)}</td>
      <td class="bar"><i style="width:${Math.round(bar(key, normKey) * 100)}%"></i></td><td class="num">#${r}<div>of ${n}</div></td></tr>`;
  }).join("")}</table><p class="muted" style="font-size:11px;margin-top:6px">Bars use each model's own scale (BM25 and k-NN after normalization, the reranker through a sigmoid). Ranks are among the ${items.length} results loaded so far; the highlighted row decided the order.</p>`;
}
const MODELS_STYLE = `<style>.dt-models{width:100%;border-collapse:collapse;font-size:13px}.dt-models td{padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
  .dt-models td div{font-size:11px;color:var(--muted)}.dt-models .num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
  .dt-models .bar{width:90px}.dt-models .bar i{display:block;height:8px;margin-top:5px;border-radius:4px;background:var(--accent)}
  .dt-models tr.final{background:var(--accent-bg)}</style>`;

// 3. Specs-first drawer: what is known about the product, and where each fact came from, before the prose; then how
// each ranking model saw it.
const drawer = {
  NAME: "Specs-first drawer + ranking models",
  async open({ item, items = [item] }) {
    close(".dt-layer");
    const p = await product(item.id);
    const el = document.createElement("aside");
    el.className = "dt-layer";
    el.innerHTML = `${STYLE}<div style="position:fixed;top:0;right:0;bottom:0;width:min(460px,94vw);background:var(--card);border-left:1px solid var(--line);box-shadow:-12px 0 30px rgba(0,0,0,.2);z-index:30;overflow:auto;padding:20px 22px 90px">
      <button class="dt-x" style="float:right" aria-label="Close">✕</button><div class="dt-crumb">${breadcrumb(p)}${conf(p)}</div>
      <h2 style="margin:8px 0 2px;font-size:20px">${esc(p.title)}</h2><div class="price" style="font-size:20px;margin-bottom:16px">${money(p.price)}</div>
      <h4 style="margin:0 0 4px;font-size:12px;color:var(--muted);text-transform:uppercase">Specifications</h4>
      <table class="dt-specs">${specs(p).map((s) => `<tr><th>${esc(s.label)}</th><td>${esc(s.value)}<div style="font-size:11px;color:var(--muted)">${s.source === "supplier" ? "from the seller's data" : `read from the ${s.field?.replace("_", " ")}: “${esc(s.quote)}”`}</div></td></tr>`).join("")}</table>
      <h4 style="margin:20px 0 4px;font-size:12px;color:var(--muted);text-transform:uppercase">Description</h4><p style="font-size:14px;line-height:1.65">${descriptionHtml(p)}</p>
      <h4 style="margin:20px 0 6px;font-size:12px;color:var(--muted);text-transform:uppercase">How the ranking models saw it</h4>${MODELS_STYLE}${modelsHtml(item, items)}
      <h4 style="margin:20px 0 8px;font-size:12px;color:var(--muted);text-transform:uppercase">Similar</h4><div class="sim">Loading…</div></div>`;
    el.querySelector(".dt-x").onclick = () => el.remove();
    document.body.append(el);
    el.querySelector(".sim").innerHTML = await simHtml(p);
  },
};

// 4. Inline expand: a full-width panel opens under the clicked card's row, keeping your place in the grid.
const inline = {
  NAME: "Inline expand",
  async open({ item, card, root }) {
    close(".dt-inline");
    const grid = root.querySelector(".a-grid");
    const cards = [...grid.querySelectorAll(".a-card")];
    const cols = getComputedStyle(grid).gridTemplateColumns.split(" ").length;
    const rowEnd = cards[Math.min(cards.length - 1, Math.floor(cards.indexOf(card) / cols) * cols + cols - 1)];
    const p = await product(item.id);
    const el = document.createElement("div");
    el.className = "dt-inline";
    el.style.cssText = "grid-column:1/-1;background:var(--card);border:1px solid var(--accent);border-radius:12px;padding:18px;display:grid;grid-template-columns:200px 1fr 1fr;gap:22px;position:relative";
    el.innerHTML = `${STYLE}<button class="dt-x" style="position:absolute;top:8px;right:12px" aria-label="Close">✕</button>${img(p, 200)}
      <div><div class="dt-crumb">${breadcrumb(p)}${conf(p)}</div><h3 style="margin:6px 0">${titleHtml(p)}</h3><div class="price" style="font-size:20px">${money(p.price)}</div>
      <p style="font-size:14px;line-height:1.6">${descriptionHtml(p, 400)}</p></div>
      <div><table class="dt-specs">${specs(p).slice(0, 6).map(specRow).join("")}</table><h4 style="margin:14px 0 6px;font-size:12px;color:var(--muted)">SIMILAR</h4><div class="sim">Loading…</div></div>`;
    el.querySelector(".dt-x").onclick = () => el.remove();
    rowEnd.after(el);
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    el.querySelector(".sim").innerHTML = await simHtml(p);
  },
};

// 5. Master-detail: the grid becomes a narrow list on the left (facets fold away), the product fills the right;
// clicking another item swaps the detail without losing the list.
const split = {
  NAME: "Master-detail split",
  async open({ item, root }) {
    const main = root.querySelector(".a-body"), grid = root.querySelector(".a-grid");
    main.style.gridTemplateColumns = "320px minmax(0, 1fr)";  // the sidebar is display:none, so it takes no column
    root.querySelector(".a-side").style.display = "none";
    grid.style.gridTemplateColumns = "1fr";
    grid.querySelectorAll(".a-img").forEach((i) => (i.style.display = "none"));
    let pane = root.querySelector(".dt-split");
    if (!pane) {
      pane = document.createElement("section");
      pane.className = "dt-split";
      pane.style.cssText = "position:sticky;top:70px;align-self:start;max-height:calc(100vh - 90px);overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px";
      main.append(pane);
    }
    grid.querySelectorAll(".a-card").forEach((c) => (c.style.outline = c.dataset.id === item.id ? "2px solid var(--accent)" : ""));
    const p = await product(item.id);
    pane.innerHTML = `${STYLE}<div style="display:flex;justify-content:space-between"><div class="dt-crumb">${breadcrumb(p)}${conf(p)}</div><button class="dt-x" aria-label="Close">✕</button></div>
      <div style="display:grid;grid-template-columns:220px 1fr;gap:20px;margin-top:10px">${img(p, 220)}<div><h2 style="margin:0 0 6px">${titleHtml(p)}</h2>
      <div class="price" style="font-size:22px">${money(p.price)}</div><table class="dt-specs" style="margin-top:10px">${specs(p).slice(0, 5).map(specRow).join("")}</table></div></div>
      <p style="font-size:14px;line-height:1.65;margin-top:16px">${descriptionHtml(p)}</p><h4 style="font-size:12px;color:var(--muted)">SIMILAR</h4><div class="sim">Loading…</div>`;
    pane.querySelector(".dt-x").onclick = () => { pane.remove(); main.style.gridTemplateColumns = ""; root.querySelector(".a-side").style.display = ""; grid.style.gridTemplateColumns = ""; grid.querySelectorAll(".a-img").forEach((i) => (i.style.display = "")); grid.querySelectorAll(".a-card").forEach((c) => (c.style.outline = "")); };
    pane.querySelector(".sim").innerHTML = await simHtml(p);
  },
};

export const DETAILS = { 1: modal, 2: page, 3: drawer, 4: inline, 5: split };
export const currentDetail = () => DETAILS[new URLSearchParams(location.search).get("detail")] ? new URLSearchParams(location.search).get("detail") : "1";
export function resetDetail(root) {
  close(".dt-layer");
  close(".dt-page");
  const body = root.querySelector(".a-body");
  if (body) body.style.display = "";
  close(".dt-inline");
  root.querySelector(".dt-split")?.remove();
}
