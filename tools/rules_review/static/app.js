/* The teachers' review page: renders docs/rules-review/content.json and saves each answer as it
   is made (PUT /mojawid/api/answers/<item>). */
"use strict";

const API = "/mojawid/api";
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const state = { me: null, content: null, answers: {}, filter: "all", items: {} };

const ar = (n) => String(n).replace(/\d/g, (d) => AR_DIGITS[d]);
const $ = (sel, root = document) => root.querySelector(sel);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(c));
  }
  return node;
}

let toastTimer = null;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.status === 204 ? null : res.json();
}

/* ---- Quran text with tajweed colours and the marked letters ---------------------------- */

function quranNodes(ex) {
  const text = ex.text;
  const cuts = new Set([0, text.length]);
  for (const [s, e] of ex.spans) { cuts.add(s); cuts.add(e); }
  if (ex.mark) { cuts.add(ex.mark[0]); cuts.add(ex.mark[1]); }
  const points = [...cuts].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i], b = points[i + 1];
    if (a === b) continue;
    const span = ex.spans.find(([s, e]) => s <= a && b <= e);
    const marked = ex.mark && ex.mark[0] <= a && b <= ex.mark[1];
    const cls = [span ? `tj-${span[2]}` : "", marked ? "mk" : ""].filter(Boolean).join(" ");
    out.push(cls ? el("span", { class: cls }, text.slice(a, b)) : text.slice(a, b));
  }
  return out;
}

function exampleNode(ex) {
  const quran = el("div", { class: "quran" },
    ex.cut_before ? el("span", { class: "cut" }, "… ") : null,
    quranNodes(ex),
    ex.cut_after ? el("span", { class: "cut" }, " …") : null);
  const expect = ex.expect
    ? el("div", { class: "expect" },
      ex.at_stop ? "ما يتوقعه التطبيق عند الوقف: " : "ما يتوقعه التطبيق وصلًا: ",
      el("b", {}, ex.expect),
      ex.notes && ex.notes.length ? ` — ${ex.notes.join("، ")}` : "")
    : null;
  return el("div", { class: "ex" }, el("div", { class: "ref" }, ex.ref), quran, expect);
}

/* ---- answers --------------------------------------------------------------------------- */

function mine(id) { return (state.answers[id] || {})[state.me.email]; }
function others(id) {
  return Object.values(state.answers[id] || {}).filter((a) => a.reviewer !== state.me.email);
}

const VERDICT_TEXT = { approve: "موافق", correct: "يحتاج تصحيحًا", note: "ملاحظة" };

function othersNode(id) {
  const rows = others(id);
  if (!rows.length) return null;
  return el("div", { class: "others" }, rows.map((a) => el("div", {},
    el("span", { class: "who" }, `${a.name}: `),
    el("span", { class: `v-${a.verdict}` }, VERDICT_TEXT[a.verdict]),
    a.correction ? el("div", { class: "txt" }, a.correction) : null)));
}

/* Keep `anchor` where it is on screen while `change` runs: whatever grows or shrinks around it,
   the page scrolls back by the difference, so nothing moves under the finger. */
function keepStill(anchor, change) {
  const before = anchor ? anchor.getBoundingClientRect().top : 0;
  change();
  if (!anchor) return;
  const shift = anchor.getBoundingClientRect().top - before;
  if (Math.abs(shift) > 0.5) window.scrollBy(0, shift);
}

function setMine(id, row) {
  state.answers[id] = state.answers[id] || {};
  if (row) state.answers[id][state.me.email] = row;
  else delete state.answers[id][state.me.email];
}

const saveTimers = {};
async function save(item, verdict, correction, anchor) {
  /* the choice shows at once; undone if the server doesn't take it */
  const card = state.items[item.id];
  const status = $(".saved", card);
  const before = mine(item.id);
  const shown = verdict === null ? null : {
    ...(before || {}), item_id: item.id, reviewer: state.me.email, name: state.me.name,
    verdict, correction, item_hash: item.hash,
  };
  setMine(item.id, shown);
  keepStill(anchor, () => { refreshItem(item); refreshCounts(); });
  status.textContent = verdict === null ? "" : "جارٍ الحفظ…";
  try {
    const path = `/answers/${encodeURIComponent(item.id)}`;
    const row = verdict === null
      ? await api(path, { method: "DELETE" })
      : await api(path, { method: "PUT", body: JSON.stringify({ verdict, correction, hash: item.hash }) });
    setMine(item.id, row);
    status.textContent = row ? "حُفظ" : "";
  } catch (err) {
    setMine(item.id, before);
    keepStill(anchor, () => { refreshItem(item); refreshCounts(); });
    status.textContent = "";
    toast("تعذّر الحفظ؛ يرجى التحقق من الاتصال");
  }
}

function saveLater(item, verdict, textarea) {
  clearTimeout(saveTimers[item.id]);
  saveTimers[item.id] = setTimeout(() => {
    const text = textarea.value.trim();
    if (verdict === "note") save(item, text ? "note" : null, text, textarea);
    else save(item, verdict, text, textarea);
  }, 700);
}

function answerNode(item) {
  const box = el("textarea", { placeholder: item.kind === "note" ? "الملاحظات" : "نص التصحيح" });
  const saved = el("div", { class: "saved" });
  const stale = el("div", { class: "stale hidden" }, "تغيّر نص هذا البند بعد إجابتك؛ يرجى مراجعته من جديد.");
  if (item.kind === "note") {
    box.addEventListener("input", () => saveLater(item, "note", box));
    return el("div", { class: "answer" }, box, saved, el("div", { class: "others-slot" }));
  }
  /* no automatic focus: on a phone it opens the keyboard and scrolls the page away */
  const ok = el("button", { type: "button", class: "ok", onclick: (e) => {
    clearTimeout(saveTimers[item.id]);
    save(item, "approve", "", e.currentTarget);
  } }, "موافق");
  const fix = el("button", { type: "button", class: "fix", onclick: (e) => {
    save(item, "correct", box.value.trim(), e.currentTarget);
  } }, "يحتاج تصحيحًا");
  const clear = el("button", { type: "button", class: "clear", onclick: (e) => {
    clearTimeout(saveTimers[item.id]);
    box.value = "";
    save(item, null, "", e.currentTarget.parentElement);
  } }, "إلغاء الإجابة");
  box.classList.add("hidden");
  box.addEventListener("input", () => saveLater(item, "correct", box));
  return el("div", { class: "answer" },
    el("div", { class: "verdicts" }, ok, fix, clear), box, stale, saved,
    el("div", { class: "others-slot" }));
}

function refreshItem(item) {
  const card = state.items[item.id];
  const a = mine(item.id);
  card.classList.toggle("is-ok", a?.verdict === "approve");
  card.classList.toggle("is-fix", a?.verdict === "correct");
  const box = $("textarea", card);
  if (item.kind === "note") {
    if (a && document.activeElement !== box) box.value = a.correction;
  } else {
    $("button.ok", card).classList.toggle("on", a?.verdict === "approve");
    $("button.fix", card).classList.toggle("on", a?.verdict === "correct");
    $("button.clear", card).classList.toggle("invisible", !a);
    box.classList.toggle("hidden", a?.verdict !== "correct");
    if (a?.verdict === "correct" && document.activeElement !== box) box.value = a.correction;
    $(".stale", card).classList.toggle("hidden", !a || a.item_hash === item.hash);
  }
  const slot = $(".others-slot", card);
  slot.replaceChildren(...[othersNode(item.id)].filter(Boolean));
}

/* ---- items, sections, counts, filters -------------------------------------------------- */

function itemNode(item) {
  const swatch = item.colour ? el("span", { class: `legend-swatch bg-${item.colour}` }) : null;
  const label = state.content.status_labels[item.status];
  const card = el("article", { class: "item", id: `i-${item.id}` },
    el("h3", {}, swatch, item.title),
    label && item.kind !== "note" ? el("span", { class: `chip ${item.status}` }, label) : null,
    item.body.length ? el("div", { class: "body" }, item.body.map((p) => el("p", {}, p))) : null,
    item.facts.length
      ? el("dl", { class: "facts" }, item.facts.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]))
      : null,
    item.examples.length ? el("div", { class: "examples" }, item.examples.map(exampleNode)) : null,
    answerNode(item));
  state.items[item.id] = card;
  return card;
}

function countable(sec) { return sec.items.filter((it) => it.kind !== "note"); }

function refreshCounts() {
  const all = state.content.sections.flatMap(countable);
  const done = all.filter((it) => mine(it.id)).length;
  $("#progress").textContent = `أُجيب عن ${ar(done)} من ${ar(all.length)}`;
  for (const sec of state.content.sections) {
    const link = $(`#toc a[href="#s-${sec.id}"]`);
    const items = countable(sec);
    const n = items.filter((it) => mine(it.id)).length;
    $(".n", link).textContent = items.length ? `${ar(n)} من ${ar(items.length)}` : "";
    link.classList.toggle("done", items.length > 0 && n === items.length);
  }
}

function visible(item) {
  if (state.filter === "todo") return item.kind !== "note" && !mine(item.id);
  if (state.filter === "correct") {
    return Object.values(state.answers[item.id] || {}).some((a) => a.verdict === "correct");
  }
  return true;
}

function applyFilter() {
  for (const sec of state.content.sections) {
    let any = false;
    for (const it of sec.items) {
      const show = visible(it);
      state.items[it.id].classList.toggle("hidden", !show);
      any ||= show;
    }
    $(`#s-${sec.id}`).classList.toggle("hidden", !any);
  }
}

function render() {
  const c = state.content;
  $("#title").textContent = c.title;
  $("#riwaya").textContent = `رواية ${c.riwaya}`;
  $("#me-name").textContent = state.me.name;
  $("#intro").replaceChildren(...c.intro.map((p) => el("p", {}, p)));
  $("#toc").replaceChildren(...c.sections.map((s) =>
    el("a", { href: `#s-${s.id}` }, s.title, el("span", { class: "n" }))));
  $("#sections").replaceChildren(...c.sections.map((s) =>
    el("section", { class: "sec", id: `s-${s.id}` },
      el("h2", {}, s.title),
      el("p", { class: "sec-intro" }, s.intro),
      s.items.map(itemNode))));
  for (const sec of c.sections) for (const it of sec.items) refreshItem(it);
  refreshCounts();
  applyFilter();
}

async function load() {
  try {
    const [me, content, rows] = await Promise.all([api("/me"), api("/content"), api("/answers")]);
    state.me = me;
    state.content = content;
    for (const r of rows) (state.answers[r.item_id] ||= {})[r.reviewer] = r;
    render();
  } catch (err) {
    $("#sections").replaceChildren(el("p", { class: "error" },
      "تعذّر تحميل الصفحة. يرجى تحديثها بعد قليل."));
  }
}

function firstOnScreen() {
  const top = $(".top").getBoundingClientRect().bottom;
  return Object.values(state.items).find((c) => {
    const r = c.getBoundingClientRect();
    return r.height > 0 && r.bottom > top;
  });
}

async function poll() {
  /* the other teacher's answers, every 30 s; one's own edits stay as typed */
  try {
    const rows = await api("/answers");
    const next = {};
    for (const r of rows) (next[r.item_id] ||= {})[r.reviewer] = r;
    const mineNow = Object.fromEntries(Object.keys(state.items).map((id) => [id, mine(id)]));
    state.answers = next;
    for (const [id, row] of Object.entries(mineNow)) setMine(id, row); /* own edits stay as shown */
    keepStill(firstOnScreen(), () => {
      for (const sec of state.content.sections) for (const it of sec.items) refreshItem(it);
      refreshCounts();
    });
  } catch (err) { /* try again next time */ }
}

for (const b of document.querySelectorAll(".filters button")) {
  b.addEventListener("click", () => {
    state.filter = b.dataset.filter;
    for (const x of document.querySelectorAll(".filters button")) x.classList.toggle("on", x === b);
    applyFilter();
  });
}

load().then(() => setInterval(() => { if (state.content && !document.hidden) poll(); }, 30000));
