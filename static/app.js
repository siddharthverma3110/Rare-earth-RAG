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

// Minimal, safe Markdown: escape first, then apply a few patterns.
function md(src) {
  const inline = (t) => esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
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
  const parts = [];
  if (data.sources?.length) {
    parts.push(`<div class="srcs">${data.sources.map((s) =>
      `<span class="src">${esc(s.title)}${s.page ? ", p." + s.page : ""}</span>`).join("")}</div>`);
  }
  if (data.trace?.length) {
    parts.push(`<details><summary>${data.trace.length} lookup${data.trace.length > 1 ? "s" : ""} used</summary>${data.trace.map((t) =>
      `<pre>${esc(t.tool)}(${esc(JSON.stringify(t.input))})\n\n${esc(JSON.stringify(t.output, null, 2).slice(0, 2500))}</pre>`).join("")}</details>`);
  }
  if (parts.length) { const m = document.createElement("div"); m.className = "meta"; m.innerHTML = parts.join(""); row.appendChild(m); }
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
    row.querySelector(".bubble").innerHTML = md(data.answer);
    addMeta(row, data);
    history.push({ role: "assistant", content: data.answer });
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
