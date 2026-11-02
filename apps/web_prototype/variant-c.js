// PROTOTYPE variant C: explain the result. Split pane: a ranked list on the left, and for the selected product its
// evidence (the listing with each extracted attribute highlighted) and how it ranked (per-stage scores) on the
// right. Question: do shoppers (and merchandisers) want the "why" beside the results? Throwaway.
import { esc, highlight, money, parsedSummary, product, search } from "./api.js";

export const NAME = "Explain the result";
const STAGES = [["bm25", "Keyword match (BM25)"], ["knn", "Meaning match (k-NN)"], ["hybrid", "Hybrid score"], ["rerank", "Reranker"]];

export function mount(root) {
  const state = { q: "merrell hiking boots", items: [], cursor: null, last: null, selected: 0 };
  root.innerHTML = `
  <style>
    .c-top{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;background:var(--card)}
    .c-top input{width:420px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
    .c-parse{font-size:13px;color:var(--muted)}.c-parse b{color:var(--ink);font-weight:600}
    .c-pane{display:grid;grid-template-columns:minmax(320px,38%) 1fr;height:calc(100vh - 58px)}
    .c-list{overflow:auto;border-right:1px solid var(--line);padding-bottom:80px}
    .c-item{display:grid;grid-template-columns:28px 1fr auto;gap:2px 10px;padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer}
    .c-item.on{background:var(--accent-bg)}.c-item .r{color:var(--muted);font-size:12px;grid-row:1/3}
    .c-item .t{font-size:14px}.c-item .s{font-size:11px;color:var(--muted)}
    .c-stage{font-size:10px;border-radius:4px;padding:1px 5px;background:var(--line)}.c-stage.head{background:var(--accent);color:#fff}
    .c-more{margin:12px;width:calc(100% - 24px);padding:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px}
    .c-detail{overflow:auto;padding:22px 28px 90px}.c-detail h2{margin:0 0 4px;font-size:22px}
    .c-sec{margin-top:22px}.c-sec h3{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 8px}
    .c-field{display:grid;grid-template-columns:120px 1fr;gap:8px;font-size:14px;line-height:1.6;padding:4px 0}.c-field span{color:var(--muted);font-size:12px}
    .c-attrs{display:flex;gap:8px;flex-wrap:wrap}.c-attr{border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px}
    .c-attr b{display:block;font-size:11px;color:var(--muted);font-weight:500}
    .c-bar{display:grid;grid-template-columns:170px 1fr 60px;gap:10px;align-items:center;font-size:13px;margin:4px 0}
    .c-bar i{display:block;height:8px;border-radius:4px;background:var(--accent)}.c-bar .track{background:var(--line);border-radius:4px}
    .c-note{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px;font-size:13px;margin-top:10px}
  </style>
  <header class="c-top"><form><input aria-label="Search"></form><div class="c-parse"></div></header>
  <div class="c-pane"><div class="c-list"></div><div class="c-detail"></div></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;
  $("form").onsubmit = (e) => { e.preventDefault(); state.q = $("input").value; state.selected = 0; run(); };
  root.addEventListener("keydown", (e) => {
    if (e.target.closest("input")) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); select(Math.max(0, Math.min(state.items.length - 1, state.selected + (e.key === "ArrowDown" ? 1 : -1)))); }
  });
  root.tabIndex = 0;

  async function run(more = false) {
    const body = await search({ q: state.q, cursor: more ? state.cursor : null, pageSize: 20, debug: true });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) state.last = body;
    renderList();
    if (!more) select(0);
  }
  function renderList() {
    const qp = state.last.query_parse;
    $(".c-parse").innerHTML = `${state.last.total.toLocaleString()} results · ` + (qp ? `read as <b>${esc(qp.keywords)}</b> ${parsedSummary(qp).map((c) => `+ <b>${esc(c.label)}</b>${c.relaxed ? " (dropped)" : ""}`).join(" ")} <span class="muted">(${qp.source}, ${qp.ms} ms)</span>` : "");
    $(".c-list").innerHTML = state.items.map((i, n) => `<div class="c-item ${n === state.selected ? "on" : ""}" data-n="${n}">
      <span class="r">${i.rank}</span><span class="t">${esc(i.title)}</span><span class="price">${money(i.price)}</span>
      <span class="s"><span class="c-stage ${i.debug?.stage}">${i.debug?.stage ?? ""}</span> ${i.debug?.scores?.rerank != null ? "rerank " + i.debug.scores.rerank.toFixed(2) : ""}</span></div>`).join("")
      + (state.cursor ? `<button class="c-more">Load more</button>` : "");
    root.querySelectorAll(".c-item").forEach((el) => el.onclick = () => select(Number(el.dataset.n)));
    root.querySelector(".c-more")?.addEventListener("click", () => run(true));
  }
  async function select(n) {
    state.selected = n;
    root.querySelectorAll(".c-item").forEach((el) => el.classList.toggle("on", Number(el.dataset.n) === n));
    root.querySelector(".c-item.on")?.scrollIntoView({ block: "nearest" });
    const item = state.items[n];
    if (!item) { $(".c-detail").innerHTML = `<p class="muted">No results.</p>`; return; }
    const p = await product(item.id);
    const spans = (field) => p.extracted_attributes.filter((a) => a.evidence_field === field).map((a) => [a.evidence_start, a.evidence_end]);
    const raw = Object.entries(p.attributes).sort().map(([k, v]) => `${k}: ${v}`).join("; ") || "(none)";
    const scores = item.debug?.scores ?? {};
    const max = Math.max(...STAGES.map(([k]) => Math.abs(scores[k] ?? 0)), 1e-9);
    const qp = state.last.query_parse;
    $(".c-detail").innerHTML = `
      <h2>${esc(p.title)}</h2><div class="muted">${esc(p.brand ?? "")} · <span class="price">${money(p.price)}</span> · ${esc(p.supplier)}</div>
      <div class="c-sec"><h3>Category</h3>${esc(p.category?.full_path ?? "not classified yet")}${p.category ? ` <span class="muted">(confidence ${p.category.confidence})</span>` : ""}</div>
      <div class="c-sec"><h3>What the listing says</h3>
        <div class="c-field"><span>Title</span><div>${highlight(p.title, spans("title"))}</div></div>
        <div class="c-field"><span>Description</span><div>${highlight((p.description ?? "").slice(0, 1500), spans("description"))}</div></div>
        <div class="c-field"><span>Supplier columns</span><div>${highlight(raw, spans("raw_attributes"))}</div></div>
        <div class="c-attrs">${p.extracted_attributes.map((a) => `<div class="c-attr"><b>${a.name}</b>${esc(a.value)}${a.unit ? " " + a.unit : ""}</div>`).join("") || `<span class="muted">No attributes extracted${p.category ? "" : " (not enriched yet)"}.</span>`}</div>
      </div>
      <div class="c-sec"><h3>Why it ranked #${item.rank} (${item.debug?.stage ?? "?"})</h3>
        ${STAGES.filter(([k]) => scores[k] != null).map(([k, label]) => `<div class="c-bar"><span>${label}</span><div class="track"><i style="width:${Math.max(3, Math.abs(scores[k]) / max * 100)}%"></i></div><span>${scores[k].toFixed(3)}</span></div>`).join("") || `<p class="muted">Scores only exist for the first page of a search.</p>`}
        ${qp?.source === "degraded" ? `<div class="c-note">The search filters couldn’t be read in time, so this is a broader match.</div>` : ""}
      </div>`;
  }
  run();
}
