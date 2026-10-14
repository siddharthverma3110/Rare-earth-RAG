const $ = (id) => document.getElementById(id);
const log = $("log"), input = $("input"), send = $("send");
let history = [], busy = false;

const STARTERS = [
  "Which rare earth elements are used in EV magnets?",
  "How did China's production change from 2022 to 2023?",
  "Why is heavy rare earth separation a bottleneck?",
  "What was the dysprosium price in 2023?",
];

function esc(s) { return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

const CITE_RE = /\[(S\d+(?:\s*,\s*S\d+)*)\]/g;

// Minimal, safe Markdown: escape first, then apply a few patterns.
function md(src, sources = {}) {
  const cites = (_, ids) => ids.split(",").map((x) => x.trim()).filter((id) => sources[id]).map((id) =>
    `<button type="button" class="cite" data-id="${id}" aria-label="Source ${id.slice(1)}: ${esc(sources[id].title)}">${id.slice(1)}</button>`).join("");
  const inline = (t) => esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(CITE_RE, cites);
  const out = []; let list = null;
  const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const line of src.split("\n")) {
    const ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (ul || ol) {
      const tag = ul ? "ul" : "ol";
      if (list !== tag) { close(); out.push(`<${tag}>`); list = tag; }
      out.push(`<li>${inline((ul || ol)[1])}</li>`);
    } else if (line.trim() === "") { close(); }
    else { close(); out.push(`<p>${inline(line.replace(/^#+\s*/, ""))}</p>`); }
  }
  close();
  return out.join("");
}

function scroll() { log.scrollTop = log.scrollHeight; }

function hello() {
  log.innerHTML = `<div class="hello"><h2>What would you like to know about rare earths?</h2>
    <p>Ask a question and the assistant will search the documents and datasets before answering.</p>
    <div class="starters">${STARTERS.map((s) => `<button type="button">${esc(s)}</button>`).join("")}</div></div>`;
  log.querySelectorAll(".starters button").forEach((b) => (b.onclick = () => ask(b.textContent)));
}

function addRow(role, html, cls = "") {
  const row = document.createElement("div");
  row.className = "row " + role;
  row.innerHTML = `<div class="bubble ${cls}">${html}</div>`;
  log.appendChild(row); scroll(); return row;
}

function addMeta(row, data) {
  if (!data.trace?.length) return;
  const m = document.createElement("div"); m.className = "meta";
  m.innerHTML = `<details><summary>${data.trace.length} lookup${data.trace.length > 1 ? "s" : ""} used</summary>${data.trace.map((t) =>
    `<pre>${esc(t.tool)}(${esc(JSON.stringify(t.input))})\n\n${esc(JSON.stringify(t.output, null, 2).slice(0, 2500))}</pre>`).join("")}</details>`;
  row.appendChild(m);
}

// ---- hover / focus / tap tooltip for in-text citations ----
const tip = document.createElement("div");
tip.id = "tip"; tip.setAttribute("role", "tooltip"); tip.hidden = true; document.body.appendChild(tip);
let tipFor = null;

function showTip(el) {
  const src = el.closest(".row")?._sources?.[el.dataset.id];
  if (!src) return;
  tipFor = el;
  const where = [src.page ? "p." + src.page : "", src.source].filter(Boolean).join(" \u00b7 ");
  tip.innerHTML = `<strong>${esc(src.title)}</strong><span>${esc(where)}</span><p>${esc(src.excerpt || "")}${(src.excerpt || "").length >= 400 ? "\u2026" : ""}</p>`;
  tip.hidden = false;
  const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
  const left = Math.max(8, Math.min(r.left + r.width / 2 - t.width / 2, window.innerWidth - t.width - 8));
  const top = r.top - t.height - 8 >= 8 ? r.top - t.height - 8 : r.bottom + 8;
  tip.style.left = left + "px"; tip.style.top = top + "px";
}
function hideTip() { tip.hidden = true; tipFor = null; }
const isCite = (e) => e.target.closest?.(".cite");
log.addEventListener("mouseover", (e) => { const c = isCite(e); if (c) showTip(c); });
log.addEventListener("mouseout", (e) => { if (isCite(e)) hideTip(); });
log.addEventListener("focusin", (e) => { const c = isCite(e); if (c) showTip(c); });
log.addEventListener("focusout", (e) => { if (isCite(e)) hideTip(); });
log.addEventListener("click", (e) => { const c = isCite(e); if (c) (tipFor === c ? hideTip() : showTip(c)); });
log.addEventListener("scroll", hideTip);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
document.addEventListener("click", (e) => { if (!e.target.closest(".cite")) hideTip(); });

// ---- charts (Chart.js) ----
const PALETTE_LIGHT = ["#6a3fb2", "#2c7a58", "#d27a12", "#2a7fbf", "#c4456b", "#6b7782"];
const PALETTE_DARK = ["#a98bec", "#6cc59b", "#f0a24a", "#6db3ea", "#ee7f9f", "#a3afb9"];
const fmt = (v) => (v == null ? "\u2014" : Number(v).toLocaleString());

function addChart(row, spec, sources) {
  const fig = document.createElement("figure");
  fig.className = "chart";
  const summary = `${spec.title}. ` + spec.series.map((s) => s.name).join(", ") + ` by ${spec.x[0]} to ${spec.x[spec.x.length - 1]}.`;
  const cite = sources[spec.cite]
    ? ` <button type="button" class="cite" data-id="${spec.cite}" aria-label="Source: ${esc(sources[spec.cite].title)}">${spec.cite.slice(1)}</button>` : "";
  fig.innerHTML = `<div class="chartbox"><canvas role="img" aria-label="${esc(summary)}"></canvas></div>
    <figcaption><span>${esc(spec.y_label)}${cite}</span><button type="button" class="ghost small">Save image</button></figcaption>
    <details><summary>View data</summary><div class="tablewrap"><table><thead><tr><th></th>${spec.series.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr></thead>
    <tbody>${spec.x.map((x, i) => `<tr><th>${esc(x)}</th>${spec.series.map((s) => `<td>${fmt(s.values[i])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
  row.appendChild(fig);
  if (!window.Chart) { fig.querySelector(".chartbox").remove(); fig.querySelector("figcaption button.small").remove(); fig.querySelector("details").open = true; return; }

  const css = getComputedStyle(document.documentElement), v = (n) => css.getPropertyValue(n).trim();
  const dark = matchMedia("(prefers-color-scheme: dark)").matches, pal = dark ? PALETTE_DARK : PALETTE_LIGHT;
  const isBar = spec.type === "bar";
  const chart = new Chart(fig.querySelector("canvas"), {
    type: spec.type,
    data: { labels: spec.x, datasets: spec.series.map((s, i) => ({
      label: s.name, data: s.values, borderColor: pal[i % pal.length], backgroundColor: pal[i % pal.length],
      borderWidth: 2.5, pointRadius: 3.5, pointHoverRadius: 5, tension: 0.2, spanGaps: true, borderRadius: isBar ? 3 : 0 })) },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: {
        title: { display: true, text: spec.title, color: v("--ink"), font: { size: 14, weight: "600" }, padding: { bottom: 12 } },
        legend: { display: spec.series.length > 1, labels: { color: v("--ink"), usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y)} ${spec.y_label}` } },
      },
      scales: {
        x: { ticks: { color: v("--muted") }, grid: { display: false }, border: { color: v("--line") } },
        y: { beginAtZero: isBar, ticks: { color: v("--muted"), callback: (t) => Number(t).toLocaleString() },
             grid: { color: v("--line") }, border: { display: false }, title: { display: true, text: spec.y_label, color: v("--muted") } },
      },
    },
    plugins: [{ id: "bg", beforeDraw(c) { const x = c.ctx; x.save(); x.globalCompositeOperation = "destination-over"; x.fillStyle = v("--card"); x.fillRect(0, 0, c.width, c.height); x.restore(); } }],
  });
  fig.querySelector("figcaption button.small").onclick = () => {
    const a = document.createElement("a");
    a.href = chart.toBase64Image("image/png", 1); a.download = spec.title.replace(/[^\w]+/g, "_").toLowerCase() + ".png"; a.click();
  };
  scroll();
}

async function ask(text) {
  text = text.trim();
  if (!text || busy) return;
  if (!history.length) log.innerHTML = "";
  busy = true; send.disabled = true; input.value = ""; input.style.height = "auto";
  addRow("user", esc(text));
  history.push({ role: "user", content: text });
  const row = addRow("bot", '<span class="dots"><span></span><span></span><span></span></span>');
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Request failed (" + res.status + ")");
    const bubble = row.querySelector(".bubble");
    row._sources = data.sources || {};
    bubble.innerHTML = md(data.answer, row._sources);
    (data.charts || []).forEach((c) => addChart(row, c, row._sources));
    addMeta(row, data);
    history.push({ role: "assistant", content: data.answer.replace(CITE_RE, "").replace(/ +([.,;:])/g, "$1") });
  } catch (e) {
    history.pop();
    const b = row.querySelector(".bubble"); b.classList.add("error");
    b.textContent = e.message + " Please try again.";
  }
  busy = false; send.disabled = false; input.focus(); scroll();
}

$("form").onsubmit = (e) => { e.preventDefault(); ask(input.value); };
input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); } };
input.oninput = () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; };
$("clear").onclick = () => { history = []; hello(); };
hello();
