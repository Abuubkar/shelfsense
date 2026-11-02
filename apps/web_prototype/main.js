// PROTOTYPE: variant switcher. ?variant=A|B|C|D, floating bar, ← → keys. Throwaway.
import * as A from "./variant-a.js";
import * as B from "./variant-b.js";
import * as C from "./variant-c.js";
import * as D from "./variant-d.js";

const VARIANTS = { A, B, C, D };
const keys = Object.keys(VARIANTS);
const app = document.getElementById("app");
const current = () => (keys.includes(new URLSearchParams(location.search).get("variant")) ? new URLSearchParams(location.search).get("variant") : "A");

function show(key) {
  const url = new URL(location);
  url.searchParams.set("variant", key);
  history.replaceState(null, "", url);
  app.innerHTML = "";
  VARIANTS[key].mount(app);
  bar.querySelector(".label").textContent = `${key} · ${VARIANTS[key].NAME}`;
}
function step(d) { show(keys[(keys.indexOf(current()) + d + keys.length) % keys.length]); }

const bar = document.createElement("div");
bar.className = "switcher";
bar.innerHTML = `<span class="tag">PROTOTYPE</span><button aria-label="Previous variant">←</button><span class="label"></span><button aria-label="Next variant">→</button>`;
bar.children[1].onclick = () => step(-1);
bar.children[3].onclick = () => step(1);
document.body.append(bar);
addEventListener("keydown", (e) => {
  if (e.target.closest("input,textarea,[contenteditable]")) return;
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
});
show(current());
