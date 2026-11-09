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
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
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
    else if (/^\s{0,3}#{1,6}\s+/.test(line)) { close(); out.push(`<h4>${inline(line.replace(/^\s*#+\s*/, ""))}</h4>`); }
    else { close(); out.push(`<p>${inline(line)}</p>`); }
  }
  close();
  return out.join("");
}

function scroll() { log.scrollTop = log.scrollHeight; }

let mode = "chat", needsCode = false;
const RESEARCH_STARTERS = [
  "Assess global supply risk for heavy rare earths",
  "How are rare earth magnets recycled, and what limits scale?",
  "Compare China's and Australia's rare earth industries",
];

function hello() {
  const r = mode === "research";
  log.innerHTML = `<div class="hello"><h2>${r ? "Run a deep research report" : "What would you like to know about rare earths?"}</h2>
    <p>${r ? "A planner runs web, academic and library searches in parallel, then writes a cited report. It takes a few minutes."
           : "Ask a question and the assistant will search the documents and datasets before answering."}</p>
    <div class="starters">${(r ? RESEARCH_STARTERS : STARTERS).map((s) => `<button type="button">${esc(s)}</button>`).join("")}</div></div>`;
  log.querySelectorAll(".starters button").forEach((b) => (b.onclick = () => run(b.textContent)));
}
const clearHello = () => log.querySelector(".hello")?.remove();
const run = (t) => (mode === "research" ? research(t) : ask(t));

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
  Chart.defaults.font.family = v("--font");
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
  clearHello();
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

// ---- deep research mode ----
const safeUrl = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : ""; } catch { return ""; } };
const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const srcLabel = (s) => s.kind === "doc" ? "Knowledge base" : s.kind === "paper"
  ? [s.authors, s.year, s.venue].filter(Boolean).join(", ") : hostOf(s.url);

function setMode(m) {
  mode = m;
  const r = m === "research";
  $("mode-chat").setAttribute("aria-selected", String(!r));
  $("mode-research").setAttribute("aria-selected", String(r));
  input.placeholder = r ? "Describe a topic to research in depth" : "Ask about rare earths";
  send.textContent = r ? "Research" : "Send";
  $("code").hidden = !(r && needsCode);
  $("modehint").textContent = r ? "Slower and uses more of the daily allowance: about 1\u20133 minutes per report." : "";
  $("modehint").classList.remove("warn");
  if (log.querySelector(".hello")) hello();
  input.focus();
}

const STEPS = ["Planning searches", "Searching the web and academic papers", "Writing the report"];
const progressHTML = () => `<ol class="steps">${STEPS.map((t, i) =>
  `<li class="step ${i === 0 ? "active" : "pending"}"><span class="dot">${i + 1}</span><div><b>${t}</b><small></small></div></li>`).join("")}</ol>
  <p class="slow">This usually takes 1\u20133 minutes. You can keep this tab open while it works.</p>`;

function setStep(bubble, n, detail) {
  bubble.querySelectorAll(".step").forEach((li, i) => {
    li.className = "step " + (i + 1 < n ? "done" : i + 1 === n ? "active" : "pending");
    li.querySelector(".dot").textContent = i + 1 < n ? "\u2713" : i + 1;
    if (i + 1 === n && detail) li.querySelector("small").textContent = detail;
  });
}

function reportMarkdown(data) {
  const refs = data.sources.map((s) => `${s.n}. ${s.title}${s.url && !s.url.startsWith("kb://") ? " - " + s.url : ""} (${srcLabel(s)})`).join("\n");
  return data.markdown + "\n\n## Sources\n" + refs + "\n";
}

function renderReport(row, data) {
  const bubble = row.querySelector(".bubble");
  const sources = {};
  data.sources.forEach((s) => (sources["S" + s.n] = { title: s.title, source: srcLabel(s), page: null, excerpt: s.snippet || "" }));
  row._sources = sources;
  bubble.className = "bubble report";
  bubble.innerHTML = md(data.markdown.replace(/\[(\d+)\](?!\()/g, "[S$1]"), sources);

  const groups = [["doc", "Knowledge base"], ["web", "Web sources"], ["paper", "Academic papers"]];
  const refs = document.createElement("div"); refs.className = "refs";
  let html = "";
  groups.forEach(([kind, label]) => {
    const list = data.sources.filter((s) => s.kind === kind);
    if (!list.length) return;
    html += `<h4>${label}</h4><ol>${list.map((s) => {
      const u = kind === "doc" ? "" : safeUrl(s.url);
      return `<li value="${s.n}"><span class="n">[${s.n}]</span><div>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>` : esc(s.title)}<span class="m">${esc(srcLabel(s))}</span></div></li>`;
    }).join("")}</ol>`;
  });
  refs.innerHTML = html || "<p class='m'>No sources were cited.</p>";
  bubble.appendChild(refs);

  const words = data.markdown.split(/\s+/).filter(Boolean).length;
  const bar = document.createElement("div"); bar.className = "meta actions";
  bar.innerHTML = `<span>${words.toLocaleString()} words \u00b7 ${data.sources.length} sources</span>
    <span class="grow"></span><button type="button" class="ghost small" data-a="copy">Copy</button>
    <button type="button" class="ghost small" data-a="dl">Download .md</button>`;
  bar.querySelector('[data-a="copy"]').onclick = async (e) => {
    try { await navigator.clipboard.writeText(reportMarkdown(data)); e.target.textContent = "Copied"; } catch { e.target.textContent = "Copy failed"; }
    setTimeout(() => (e.target.textContent = "Copy"), 1600);
  };
  bar.querySelector('[data-a="dl"]').onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([reportMarkdown(data)], { type: "text/markdown" }));
    a.download = "rare-earths-research-report.md"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
  row.appendChild(bar);

  if (data.follow_ups?.length) {
    const f = document.createElement("div"); f.className = "followups";
    f.innerHTML = `<span>Research next:</span>` + data.follow_ups.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
    f.querySelectorAll("button").forEach((b) => (b.onclick = () => { setMode("research"); input.value = b.textContent; input.oninput(); input.focus(); }));
    row.appendChild(f);
  }
  scroll();
}

async function research(text) {
  text = text.trim();
  if (text.length < 3 || busy) return;
  const code = $("code").value.trim();
  if (needsCode && !code) { const h = $("modehint"); h.textContent = "Enter the access code to use deep research."; h.classList.add("warn"); $("code").focus(); return; }
  clearHello();
  busy = true; send.disabled = true; input.value = ""; input.style.height = "auto";
  addRow("user", esc(text));
  const row = addRow("bot", progressHTML()); row.classList.add("research");
  const bubble = row.querySelector(".bubble");
  const fail = (msg) => { bubble.className = "bubble error"; bubble.textContent = msg + " Please try again."; };
  let finished = false;
  try {
    const res = await fetch("/api/research", { method: "POST", headers: { "Content-Type": "application/json", "X-Access-Code": code }, body: JSON.stringify({ query: text }) });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(typeof d.detail === "string" ? d.detail : res.status === 422 ? "Please enter a topic of 3 to 500 characters." : "Request failed (" + res.status + ").");
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let m; try { m = JSON.parse(line); } catch { continue; }
        if (m.type === "status") {
          const t = m.data;
          if (t.startsWith("Planning")) setStep(bubble, 1);
          else if (t.startsWith("Planned")) { const x = t.match(/\((\d+) web, (\d+) academic, (\d+) library\)/); setStep(bubble, 2, x ? `${x[1]} web, ${x[2]} academic and ${x[3]} library searches in parallel` : ""); }
          else if (t.startsWith("Searches complete")) setStep(bubble, 3);
        } else if (m.type === "error") { finished = true; fail(m.data); }
        else if (m.type === "report") { finished = true; renderReport(row, m.data); }
      }
    }
    if (!finished) fail("The connection ended before the report was finished.");
  } catch (e) { fail(e.message); }
  busy = false; send.disabled = false; input.focus(); scroll();
}

$("form").onsubmit = (e) => { e.preventDefault(); run(input.value); };
input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(input.value); } };
input.oninput = () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; };
$("clear").onclick = () => { history = []; hello(); };
$("mode-chat").onclick = () => setMode("chat");
$("mode-research").onclick = () => setMode("research");
try { $("code").value = sessionStorage.getItem("rc") || ""; } catch {}
$("code").oninput = () => { try { sessionStorage.setItem("rc", $("code").value); } catch {} $("modehint").classList.remove("warn"); };
fetch("/api/config").then((r) => r.json()).then((c) => { needsCode = !!c.research_requires_code; setMode(mode); }).catch(() => {});
hello();
