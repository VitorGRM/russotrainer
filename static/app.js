"use strict";

/* LinguaLab Russo · interface do curso temático.
   Galeria de fichas -> gaveta com o estado do tema -> sessão Estudar/Revisar. */

const $ = (selector, root = document) => root.querySelector(selector);
const number = new Intl.NumberFormat("pt-BR");
const CYRILLIC_WORD = /([А-Яа-яЁё́]+(?:-[А-Яа-яЁё́]+)*)/g;

const state = {
  boot: null,
  themes: [],
  settings: {},
  openTheme: null,
  session: null,
};

// ------------------------------------------------------------------ utilidades
async function api(path, options = {}) {
  const init = { ...options };
  if (init.body && typeof init.body !== "string") {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) throw new Error(data.error || `Erro ${response.status}`);
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style" && typeof value === "object") {
      for (const [prop, val] of Object.entries(value)) {
        if (prop.startsWith("--")) node.style.setProperty(prop, val);
        else node.style[prop] = val;
      }
    }
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Texto com palavras russas clicáveis (abrem o dicionário). */
function ruText(text, className = "ru") {
  const span = el("span", { class: className });
  String(text || "").split(CYRILLIC_WORD).forEach((part, index) => {
    if (index % 2 === 1) span.append(el("span", { class: "clickable-word", dataset: { word: part } }, part));
    else if (part) span.append(part);
  });
  return span;
}

function percent(part, total) {
  return total ? Math.round((part / total) * 100) : 0;
}

function toast(message) {
  const node = el("div", { class: "toast", role: "status" }, message);
  document.body.append(node);
  setTimeout(() => node.remove(), 3200);
}

function themeById(id) {
  return state.themes.find((t) => t.id === id);
}

function meter(seen, mastered, total) {
  return el("div", { class: "meter" },
    el("span", { class: "seen", style: { width: `${percent(seen, total)}%` } }),
    el("span", { class: "mastered", style: { width: `${percent(mastered, total)}%` } }));
}

// ------------------------------------------------------------------ áudio
let currentAudio = null;
function playAudio(text, button, voice = "") {
  if (!text) return;
  if (currentAudio) currentAudio.pause();
  const url = `/api/tts?text=${encodeURIComponent(text)}${voice ? `&voice=${voice}` : ""}`;
  const audio = new Audio(url);
  currentAudio = audio;
  button?.classList.add("playing");
  audio.addEventListener("ended", () => button?.classList.remove("playing"));
  audio.addEventListener("error", () => {
    button?.classList.remove("playing");
    toast("Áudio indisponível agora. Verifique a conexão com a internet.");
  });
  audio.play().catch(() => button?.classList.remove("playing"));
}

function audioButton(text, label = "Ouvir", voice = "") {
  const button = el("button", { class: "audio-btn", type: "button", "aria-label": label, title: label },
    svgIcon("M8 5v14l11-7z"));
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    playAudio(text, button, voice);
  });
  return button;
}

function svgIcon(path) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", path);
  svg.append(p);
  return svg;
}

// ------------------------------------------------------------------ início
async function boot() {
  try {
    state.boot = await api("/api/bootstrap");
  } catch (error) {
    $("#catalog").replaceChildren(el("p", { class: "loading" }, `Não foi possível carregar o curso: ${error.message}`));
    return;
  }
  applyOverview(state.boot);
  const c = state.boot.counts;
  $("#sources").textContent =
    `${number.format(c.entries)} verbetes do OpenRussian, ${number.format(c.studyable)} com tradução e prontos para estudo, ` +
    `${number.format(c.expressions)} expressões e construções, ${number.format(c.structures)} exercícios de estrutura. ` +
    "Fontes: OpenRussian (CC BY-SA 4.0), Wiktionary (CC BY-SA 3.0), WordNet de Princeton e OpenWN-PT, FrequencyWords (OpenSubtitles).";
  if (state.boot.features.self_update) checkUpdate();
}

function applyOverview(data) {
  state.themes = data.themes;
  state.settings = data.settings;
  renderStats(data.totals);
  renderCatalog();
}

async function refreshOverview() {
  applyOverview(await api("/api/themes"));
}

function renderStats(totals) {
  if (!totals) return;
  const parts = [
    el("span", {}, el("b", {}, number.format(totals.seen)), " estudados"),
    el("span", {}, el("b", {}, number.format(totals.mastered)), " dominados"),
    el("span", {}, el("b", {}, number.format(totals.due)), " para revisar"),
  ];
  if (totals.streak) parts.push(el("span", {}, el("b", {}, totals.streak), totals.streak === 1 ? " dia seguido" : " dias seguidos"));
  $("#topbar-stats").replaceChildren(...parts);
}

// ------------------------------------------------------------------ galeria
function renderCatalog() {
  const catalog = $("#catalog");
  const open = state.openTheme;
  catalog.replaceChildren(...state.themes.map(themeCard));
  if (open && themeById(open)) {
    const card = catalog.querySelector(`[data-theme-id="${open}"]`);
    if (card) placeDrawer(card, themeById(open));
  }
}

function themeCard(theme) {
  const card = el("button", {
    class: "card", type: "button", role: "listitem", "aria-expanded": "false",
    dataset: { themeId: theme.id, icon: `${theme.icon}  ${theme.name.split(" ")[0]}` },
    style: { "--tab": theme.color },
    onclick: () => toggleDrawer(theme.id),
  },
  el("span", { class: "card-ru" }, theme.ru),
  el("span", { class: "card-pt" }, theme.name),
  el("span", { class: "card-preview" }, theme.preview.join(", ")),
  meter(theme.seen, theme.mastered, theme.total),
  el("span", { class: "card-foot" },
    el("span", {}, `${number.format(theme.seen)} de ${number.format(theme.total)}`),
    theme.due ? el("span", { class: "due" }, `${number.format(theme.due)} para revisar`) : el("span", {}, `${percent(theme.seen, theme.total)}%`)));
  card.style.setProperty("--tab", theme.color);
  return card;
}

function toggleDrawer(themeId) {
  const catalog = $("#catalog");
  catalog.querySelector(".drawer")?.remove();
  catalog.querySelectorAll(".card").forEach((c) => c.setAttribute("aria-expanded", "false"));
  if (state.openTheme === themeId) {
    state.openTheme = null;
    return;
  }
  state.openTheme = themeId;
  const card = catalog.querySelector(`[data-theme-id="${themeId}"]`);
  placeDrawer(card, themeById(themeId));
}

/** A gaveta entra depois da última ficha da mesma fileira e aponta para a ficha aberta. */
function placeDrawer(card, theme) {
  const catalog = $("#catalog");
  catalog.querySelector(".drawer")?.remove();
  card.setAttribute("aria-expanded", "true");
  const cards = [...catalog.querySelectorAll(".card")];
  const top = card.offsetTop;
  let anchor = card;
  for (const other of cards) if (other.offsetTop === top) anchor = other;
  const drawer = renderDrawer(theme);
  anchor.after(drawer);
  const offset = card.offsetLeft - catalog.offsetLeft + card.offsetWidth / 2 - 8;
  drawer.style.setProperty("--notch-x", `${offset}px`);
  drawer.style.setProperty("--tab", theme.color);
  requestAnimationFrame(() => {
    const rect = drawer.getBoundingClientRect();
    if (rect.bottom > window.innerHeight) window.scrollBy({ top: Math.min(rect.bottom - window.innerHeight + 24, rect.top - 90), behavior: "smooth" });
  });
}

window.addEventListener("resize", () => {
  if (!state.openTheme || !$("#view-gallery").checkVisibility?.()) return;
  const card = $(`#catalog [data-theme-id="${state.openTheme}"]`);
  if (card) placeDrawer(card, themeById(state.openTheme));
});

function renderDrawer(theme) {
  const hasReview = theme.seen > 0;
  const modules = theme.modules || [];
  const studyButton = el("button", {
    class: `btn${modules.length ? "" : " primary"}`, type: "button", disabled: theme.new_words === 0,
    onclick: () => startSession(theme.id, "study"),
  }, "Vocabulário novo", el("small", {}, `${number.format(theme.new_words)} palavras`));
  const reviewButton = el("button", {
    class: "btn", type: "button", disabled: !hasReview,
    onclick: () => startSession(theme.id, "review", theme.due === 0),
  }, "Revisar", el("small", {}, theme.due ? `${number.format(theme.due)} para hoje` : hasReview ? "revisão extra" : "nada estudado ainda"));

  const aspects = el("div", { class: "aspects" }, ...theme.aspects.filter((a) => a.total).map((aspect) =>
    el("button", { class: "aspect", type: "button", onclick: () => openThemeCatalog(theme, aspect.id), title: "Ver a lista" },
      el("span", { class: "aspect-label" }, aspect.label),
      el("span", { class: "aspect-num" }, `${percent(aspect.seen, aspect.total)}% · ${number.format(aspect.seen)} de ${number.format(aspect.total)}`),
      meter(aspect.seen, aspect.mastered, aspect.total))));

  const minIndex = state.boot.levels.indexOf(state.settings.min_level);
  const levels = el("div", { class: "levels" }, ...state.boot.levels.map((level, index) => {
    const info = theme.levels.find((l) => l.level === level);
    return el("div", { class: `level${index < minIndex || !info ? " off" : ""}` },
      el("b", {}, level),
      el("small", {}, info ? `${number.format(info.seen)}/${number.format(info.total)}` : "fora do filtro"));
  }));

  const side = el("div", { class: "side" },
    el("h3", {}, "Vocabulário por nível"), levels);
  if (theme.grammar_lessons?.length) {
    side.append(el("h3", {}, "Aulas de gramática ligadas ao tema"),
      el("div", { class: "lessons" }, ...theme.grammar_lessons.map((lesson) =>
        el("button", { class: "lesson-link", type: "button", onclick: () => openLesson(lesson.id) }, lesson.title))));
  }
  side.append(el("button", { class: "btn", type: "button", onclick: () => openThemeCatalog(theme, "") }, "Ver todas as palavras do tema"));

  return el("section", { class: "drawer", "aria-label": `Tema ${theme.name}` },
    el("div", { class: "drawer-head" },
      el("div", {},
        el("h2", { class: "ru" }, theme.ru),
        el("div", { class: "pt" }, theme.name),
        el("p", {}, theme.description)),
      el("div", { class: "drawer-actions" }, studyButton, reviewButton)),
    ...modules.map((module) => lessonModuleCard(theme, module)),
    el("div", { class: "drawer-grid" },
      el("div", {}, aspects,
        el("div", { class: "legend" },
          el("span", {}, el("i", { style: { background: `color-mix(in srgb, ${theme.color} 40%, transparent)` } }), "estudado"),
          el("span", {}, el("i", { style: { background: theme.color } }), "dominado (sobreviveu a revisões de 7 e 14 dias)"))),
      side));
}

// ------------------------------------------------------------------ catálogo do tema
async function openThemeCatalog(theme, aspect) {
  const body = el("div", { style: { "--tab": theme.color } });
  const list = el("div", { class: "item-list" });
  const more = el("button", { class: "btn", type: "button" }, "Carregar mais");
  let offset = 0;
  let current = aspect;
  const tabs = el("div", { class: "tabs" });
  const tabDefs = [{ id: "", label: "Todas as palavras" }, ...state.boot.aspects.map((a) => ({ id: a.id, label: a.label }))];
  const renderTabs = () => tabs.replaceChildren(...tabDefs.map((t) =>
    el("button", { type: "button", "aria-pressed": String(t.id === current), onclick: () => { current = t.id; offset = 0; list.replaceChildren(); renderTabs(); load(); } }, t.label)));
  const load = async () => {
    more.disabled = true;
    const data = await api(`/api/theme/items?theme=${theme.id}&aspect=${current}&offset=${offset}`);
    for (const item of data.items) {
      const dot = el("span", { class: `status-dot${item.stage === null ? "" : item.stage >= 4 ? " mastered" : " seen"}`,
        title: item.stage === null ? "ainda não estudado" : item.stage >= 4 ? "dominado" : "estudado" });
      const row = el("button", { class: "item-row", type: "button" }, dot,
        el("span", { class: "ru" }, item.ru || item.accented),
        el("span", {}, item.pt),
        el("small", {}, item.level || ""));
      if (item.item_id.startsWith("w:")) row.addEventListener("click", () => openWord(Number(item.item_id.slice(2))));
      else row.disabled = true;
      list.append(row);
    }
    offset += data.items.length;
    more.hidden = offset >= data.total;
    more.disabled = false;
    count.textContent = `${number.format(data.total)} itens · filtro de nível: a partir de ${state.settings.min_level}`;
  };
  const count = el("p", { class: "hint" });
  more.addEventListener("click", load);
  renderTabs();
  body.append(el("h2", { id: "modal-title", class: "ru" }, theme.ru), el("p", {}, theme.name), tabs, count, list, el("div", { class: "next-row" }, more));
  openModal(body);
  await load();
}

// ------------------------------------------------------------------ palavra
function formsTable(word) {
  const f = word.forms || {};
  const rows = [];
  const cases = [["nom", "nominativo"], ["gen", "genitivo"], ["dat", "dativo"], ["acc", "acusativo"], ["inst", "instrumental"], ["prep", "preposicional"]];
  if (word.pos === "noun") {
    if (!cases.some(([c]) => f[`sg_${c}`] || f[`pl_${c}`])) return null;
    rows.push(["", "singular", "plural"]);
    for (const [c, label] of cases) rows.push([label, f[`sg_${c}`] || "—", f[`pl_${c}`] || "—"]);
  } else if (word.pos === "verb") {
    const persons = [["sg1", "я"], ["sg2", "ты"], ["sg3", "он / она"], ["pl1", "мы"], ["pl2", "вы"], ["pl3", "они"]];
    if (!persons.some(([p]) => f[`presfut_${p}`])) return null;
    rows.push(["", word.aspect === "perfectivo" ? "futuro" : "presente", ""]);
    for (const [p, pronoun] of persons) rows.push([pronoun, f[`presfut_${p}`] || "—", ""]);
    rows.push(["passado", [f.past_m, f.past_f, f.past_n, f.past_pl].filter(Boolean).join(" · "), ""]);
    rows.push(["imperativo", [f.imperative_sg, f.imperative_pl].filter(Boolean).join(" · "), ""]);
  } else if (word.pos === "adjective") {
    if (!f.decl_m_nom) return null;
    rows.push(["", "masc.", "fem.", "neutro", "plural"]);
    for (const [c, label] of cases) rows.push([label, f[`decl_m_${c}`] || "—", f[`decl_f_${c}`] || "—", f[`decl_n_${c}`] || "—", f[`decl_pl_${c}`] || "—"]);
    const short = [f.short_m, f.short_f, f.short_n, f.short_pl].filter(Boolean);
    if (short.length) rows.push(["forma curta", ...short]);
    if (f.comparative) rows.push(["comparativo", f.comparative]);
  } else {
    return null;
  }
  const table = el("table", { class: "forms-table" });
  rows.forEach((row, index) => {
    const tr = el("tr");
    row.forEach((cell, cellIndex) => {
      if (index === 0 || cellIndex === 0) tr.append(el("th", {}, cell));
      else tr.append(el("td", {}, cell));
    });
    table.append(tr);
  });
  return el("details", { class: "forms" }, el("summary", {}, word.pos === "verb" ? "Conjugação" : "Declinação"), table);
}

function wordCard(word, extra = null) {
  const meta = el("div", { class: "meta" },
    el("span", { class: "pill" }, word.pos_label),
    word.gender ? el("span", { class: "pill" }, word.gender) : null,
    word.aspect ? el("span", { class: "pill" }, word.aspect) : null,
    el("span", { class: "pill" }, `nível ${word.level}`),
    ...(word.themes || []).map((id) => {
      const theme = themeById(id);
      return theme ? el("span", { class: "pill theme", style: { "--dot": theme.color } }, theme.name) : null;
    }));
  const meanings = (word.pt || "").split(";").map((m) => m.trim()).filter(Boolean);
  return el("div", { class: "word-card" },
    el("div", { class: "headword" }, el("span", { class: "ru" }, word.accented), audioButton(word.lemma, `Ouvir ${word.lemma}`)),
    el("div", { class: "meaning" }, meanings.length ? meanings.join("; ") : "Sem tradução em português nesta base."),
    meta,
    word.partner?.length ? el("div", { class: "partner" }, word.pos === "verb" ? "Par aspectual: " : "Forma correspondente: ", el("span", { class: "ru" }, word.partner.join(", "))) : null,
    extra,
    formsTable(word));
}

async function openWord(id) {
  const word = await api(`/api/word?id=${id}`);
  const status = word.state
    ? el("p", { class: "hint" }, word.state.stage >= 4 ? "Dominada." : `Estudada · estágio ${word.state.stage} de 8 da revisão espaçada.`)
    : el("p", { class: "hint" }, word.study ? "Ainda não estudada." : "Fica fora das sessões (nome próprio, palavrão ou sem tradução).");
  openModal(el("div", {}, el("span", { id: "modal-title", hidden: true }, word.lemma), wordCard(word, status)));
}

// ------------------------------------------------------------------ aula de gramática
async function openLesson(unitId) {
  const lesson = await api(`/api/lesson?unit_id=${encodeURIComponent(unitId)}`);
  const body = el("div", {}, el("h2", { id: "modal-title" }, lesson.title));
  if (lesson.description) body.append(el("p", { class: "hint" }, lesson.description));
  const fullAudio = el("button", { class: "btn", type: "button" }, "Ouvir a aula inteira");
  let lessonAudio = null;
  fullAudio.addEventListener("click", () => {
    if (lessonAudio && !lessonAudio.paused) { lessonAudio.pause(); fullAudio.textContent = "Ouvir a aula inteira"; return; }
    lessonAudio = new Audio(`/api/lesson-audio?unit_id=${encodeURIComponent(unitId)}`);
    fullAudio.textContent = "Gerando áudio… (até 1 minuto na primeira vez)";
    lessonAudio.addEventListener("playing", () => { fullAudio.textContent = "Pausar"; });
    lessonAudio.addEventListener("ended", () => { fullAudio.textContent = "Ouvir a aula inteira"; });
    lessonAudio.addEventListener("error", () => { fullAudio.textContent = "Áudio indisponível"; });
    lessonAudio.play().catch(() => {});
  });
  body.append(fullAudio);
  (lesson.grammar || []).forEach((block) => {
    const section = el("section", { class: "lesson-block" }, el("h3", {}, block.title || ""));
    (block.paragraphs || []).forEach((p) => section.append(el("p", {}, ruText(p, ""))));
    if (block.examples?.length) {
      section.append(el("div", { class: "examples" }, ...block.examples.map((ex) =>
        el("div", { class: "example-row" }, audioButton(ex.ru), el("div", {}, ruText(ex.ru), el("small", {}, ex.pt), ex.note ? el("small", {}, ex.note) : null)))));
    }
    if (block.pitfalls?.length) section.append(el("ul", { class: "pitfalls" }, ...block.pitfalls.map((p) => el("li", {}, ruText(p, "")))));
    body.append(section);
  });
  const tables = lesson.memory_tables || (lesson.memory_table ? [lesson.memory_table] : []);
  tables.forEach((t) => {
    const table = el("table", { class: "memory-table" }, el("tr", {}, ...(t.columns || []).map((c) => el("th", {}, c))),
      ...(t.rows || []).map((r) => el("tr", {}, ...r.map((c) => el("td", {}, ruText(c, ""))))));
    body.append(el("h3", {}, t.title || "Tabela"), table, t.note ? el("p", { class: "hint" }, t.note) : null);
  });
  if (lesson.source_note) body.append(el("p", { class: "hint" }, lesson.source_note));
  openModal(body, () => lessonAudio?.pause());
}

// ------------------------------------------------------------------ modal, dicionário, busca
let modalCleanup = null;
function openModal(content, onClose = null) {
  modalCleanup = onClose;
  $("#modal-body").replaceChildren(content);
  $("#modal").hidden = false;
  $(".modal-panel").scrollTop = 0;
  $(".modal-close").focus();
}
function closeModal() {
  $("#modal").hidden = true;
  if (modalCleanup) modalCleanup();
  modalCleanup = null;
}
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-close]")) closeModal();
});

document.addEventListener("click", async (event) => {
  const word = event.target.closest(".clickable-word");
  const popover = $("#dict-popover");
  if (!word) {
    if (!event.target.closest("#dict-popover")) popover.hidden = true;
    return;
  }
  event.stopPropagation();
  const rect = word.getBoundingClientRect();
  popover.style.left = `${Math.min(rect.left, window.innerWidth - 380)}px`;
  popover.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 200)}px`;
  popover.replaceChildren(el("p", { class: "loading" }, "Procurando…"));
  popover.hidden = false;
  const data = await api(`/api/dictionary?word=${encodeURIComponent(word.dataset.word)}`).catch(() => ({ entries: [] }));
  if (!data.entries.length) {
    popover.replaceChildren(el("p", {}, `«${word.dataset.word}» não está no dicionário.`));
    return;
  }
  popover.replaceChildren(...data.entries.map((entry) => el("div", { class: "entry" },
    el("div", {}, el("span", { class: "ru" }, entry.accented), " ", audioButton(entry.lemma)),
    el("div", {}, entry.pt || "sem tradução"),
    el("small", {}, [entry.pos_label, entry.gender, entry.aspect, `nível ${entry.level}`, ...(entry.grammar || [])].filter(Boolean).join(" · ")),
    el("div", {}, el("button", { class: "text-button", type: "button", onclick: () => { popover.hidden = true; openWord(entry.id); } }, "Abrir verbete")))));
});

let searchTimer = null;
$("#search-input").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  const query = event.target.value.trim();
  const box = $("#search-results");
  if (query.length < 2) { box.hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const data = await api(`/api/search?q=${encodeURIComponent(query)}`).catch(() => ({ results: [] }));
    box.replaceChildren(...(data.results.length ? data.results.map((r) =>
      el("button", { type: "button", onclick: () => { box.hidden = true; openWord(r.id); } },
        el("span", { class: "ru" }, r.accented), el("span", {}, r.pt || "—"), el("small", {}, `${r.pos_label} · ${r.level}`)))
      : [el("div", { class: "search-empty" }, "Nada encontrado.")]));
    box.hidden = false;
  }, 220);
});
$("#search-form").addEventListener("submit", (event) => event.preventDefault());
document.addEventListener("click", (event) => {
  if (!event.target.closest("#search-form")) $("#search-results").hidden = true;
});

// ------------------------------------------------------------------ preferências
function currentColorMode() {
  return document.documentElement.dataset.theme || "system";
}
function setColorMode(mode) {
  if (mode === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  try {
    if (mode === "system") localStorage.removeItem("lingualab-theme");
    else localStorage.setItem("lingualab-theme", mode);
  } catch (_) { /* sem armazenamento: vale só nesta janela */ }
}

$("#settings-button").addEventListener("click", () => {
  const levelSelect = el("select", {}, ...state.boot.levels.map((level) =>
    el("option", { value: level, selected: level === state.settings.min_level }, {
      A2: "A2 · incluir o vocabulário básico", B1: "B1 · intermediário (recomendado)", B2: "B2 · intermediário superior",
      C1: "C1 · avançado", C2: "C2 · só vocabulário raro",
    }[level])));
  const sizeSelect = el("select", {}, ...[4, 6, 8, 10, 12, 16, 20].map((n) =>
    el("option", { value: n, selected: n === Number(state.settings.session_size) }, `${n} palavras novas por sessão`)));
  const modes = [["system", "Sistema"], ["light", "Claro"], ["dark", "Escuro"]];
  const segmented = el("div", { class: "segmented" }, ...modes.map(([mode, label]) =>
    el("button", { type: "button", "aria-pressed": String(currentColorMode() === mode), onclick: (e) => {
      setColorMode(mode);
      segmented.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      e.currentTarget.setAttribute("aria-pressed", "true");
    } }, label)));
  const save = el("button", { class: "btn primary", type: "button", onclick: async () => {
    state.settings = await api("/api/settings", { body: { min_level: levelSelect.value, session_size: Number(sizeSelect.value) } });
    closeModal();
    await refreshOverview();
    toast("Preferências salvas.");
  } }, "Salvar");
  openModal(el("div", {},
    el("h2", { id: "modal-title" }, "Preferências"),
    el("div", { class: "settings-grid" },
      el("label", {}, "Nível mínimo do vocabulário", levelSelect,
        el("small", {}, "Os níveis são estimados pela frequência de uso. Palavras abaixo do mínimo ficam fora das sessões e das porcentagens.")),
      el("label", {}, "Tamanho da sessão de estudo", sizeSelect),
      el("div", { class: "settings-grid" }, el("strong", {}, "Aparência"), segmented)),
    el("div", { class: "next-row" }, save)));
});

// ------------------------------------------------------------------ sessão
async function startSession(themeId, mode, extra = false) {
  const theme = themeById(themeId);
  let data;
  try {
    data = await api(`/api/session?theme=${themeId}&mode=${mode}${extra ? "&extra=1" : ""}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  if (!data.steps.length) {
    toast(mode === "study" ? "Não há itens novos neste tema com o filtro de nível atual." : "Nada para revisar neste tema.");
    return;
  }
  state.session = { theme, mode, steps: data.steps, index: 0, results: new Map(), retried: new Set(), introduced: 0, answered: 0 };
  $("#view-gallery").hidden = true;
  $("#view-session").hidden = false;
  $("#view-session").style.setProperty("--tab", theme.color);
  $("#session-title").replaceChildren(mode === "study" ? "Vocabulário novo · " : "Revisar · ", theme.name, el("span", { class: "ru" }, theme.ru));
  window.scrollTo(0, 0);
  renderStep();
}

function endSession() {
  state.session = null;
  stopAllAudio();
  $("#view-session").hidden = true;
  $("#view-gallery").hidden = false;
  refreshOverview().catch(() => {});
}
$("#session-close").addEventListener("click", endSession);
$("#home-button").addEventListener("click", () => { if (state.session) endSession(); });

function updateProgress() {
  const s = state.session;
  const total = s.steps.length;
  $("#session-progress-bar").style.width = `${percent(s.index, total)}%`;
  $("#session-count").textContent = `${Math.min(s.index + 1, total)} / ${total}`;
}

function renderStep() {
  const s = state.session;
  updateProgress();
  const stage = $("#stage");
  if (s.index >= s.steps.length) {
    stage.replaceChildren(renderSummary());
    return;
  }
  const step = s.steps[s.index];
  let node;
  const lessonRenderers = {
    part_intro: renderPartIntro, warmup: renderWarmup, vocab: renderVocab, grammar: renderGrammar, listen: renderListen,
    transcript: renderTranscript, translation: renderTranslation, cloze: renderCloze, match: renderMatch,
    shadow: renderShadow, produce: renderProduce, part_end: renderPartEnd,
  };
  if (lessonRenderers[step.type]) node = lessonRenderers[step.type](step);
  else if (step.type === "intro") node = renderIntro(step);
  else if (step.type === "flashcard") node = renderFlashcard(step);
  else if (step.type === "order") node = renderOrder(step);
  else if (step.type === "input") node = renderInput(step);
  else node = renderChoice(step);
  stage.replaceChildren(node);
  const focusable = stage.querySelector("[data-autofocus]") || stage.querySelector("button, input");
  focusable?.focus();
  if (step.audio_lines && step.exercise === "dictation") {
    setTimeout(() => stage.querySelector(".player-play")?.click(), 300);
  }
  if (step.audio && ["audio", "hear", "listening", "vocab"].includes(step.exercise)) {
    const button = stage.querySelector(".prompt-audio .audio-btn");
    setTimeout(() => playAudio(step.audio, button), 250);
  }
}

function next() {
  stopAllAudio();
  state.session.index += 1;
  renderStep();
}

function kindLabel(step) {
  const labels = { verbos: "verbo", substantivos: "substantivo", adjetivos: "adjetivo", outros: "outra classe", estruturas: "estrutura", expressoes: "expressão" };
  if (step.kind === "structure") return step.unit_title ? `Estrutura · ${step.unit_title}` : "Estrutura";
  if (step.kind === "construction") return "Construção";
  if (step.kind === "lesson") return step.phase || "Aula";
  if (step.kind === "expression") return "Expressão";
  return labels[step.aspect] || "Palavra";
}

function renderIntro(step) {
  const continueButton = el("button", { class: "btn primary", type: "button", "data-autofocus": true, onclick: async () => {
    continueButton.disabled = true;
    await api("/api/seen", { body: { item_id: step.item_id, theme_id: step.theme_id } }).catch(() => {});
    state.session.introduced += 1;
    next();
  } }, "Continuar");
  let content;
  if (step.kind === "word") {
    content = wordCard(step.word);
    setTimeout(() => playAudio(step.word.lemma, $(".word-card .audio-btn")), 200);
  } else if (step.kind === "construction") {
    const c = step.construction;
    content = el("div", { class: "construction" },
      el("div", { class: "headword" }, ruText(c.head), " "),
      el("p", { class: "meaning" }, c.pt),
      c.regency ? el("p", {}, ruText(c.regency), c.case ? el("small", { class: "hint" }, ` · ${c.case}`) : null) : null,
      c.chunk ? el("p", {}, ruText(c.chunk), " ", audioButton(c.chunk), el("br"), el("small", { class: "hint" }, c.chunk_pt || "")) : null,
      c.example ? el("div", { class: "example" }, ruText(c.example.ru), " ", audioButton(c.example.ru), el("br"), el("small", {}, c.example.pt), c.example.note ? el("p", { class: "hint" }, c.example.note) : null) : null,
      c.form_note ? el("p", {}, ruText(c.form_note, "")) : null,
      c.trap ? el("p", { class: "trap" }, ruText(c.trap, "")) : null);
  } else {
    content = el("div", {},
      el("div", { class: "headword" }, el("span", { class: "prompt ru" }, ruText(step.expression.ru)), " ", audioButton(step.expression.ru)),
      el("p", { class: "meaning" }, step.expression.pt));
    setTimeout(() => playAudio(step.expression.ru, $(".panel .audio-btn")), 200);
  }
  return el("div", { class: "panel" },
    el("span", { class: "kind-tag" }, step.kind === "word" ? "Palavra nova" : step.kind === "construction" ? "Construção nova" : "Expressão nova"),
    content,
    el("div", { class: "next-row" }, continueButton));
}

function promptBlock(step) {
  const block = el("div", {});
  block.append(el("span", { class: "kind-tag" }, kindLabel(step)));
  if (step.instruction) block.append(el("div", { class: "instruction" }, step.instruction));
  if (step.audio_lines) block.append(el("div", { class: "listen-box" }, linePlayer(step.audio_lines, { label: step.audio_lines.length > 1 ? "Ouvir o diálogo" : "Ouvir", compact: true })));
  if (step.context) {
    block.append(el("div", { class: "context" },
      step.context_title ? el("h3", { class: "ru" }, step.context_title) : null,
      ...step.context.split("\n\n").map((p) => el("p", {}, ruText(p, "")))));
  }
  if (step.wrong_sentence) block.append(el("div", { class: "wrong-label" }, "Frase com erro:"));
  const promptRow = el("div", { class: "prompt-audio" });
  if (step.prompt) {
    const long = step.prompt.length > 40;
    promptRow.append(step.prompt_ru ? el("div", { class: `prompt ru${long ? " long" : ""}` }, ruText(step.prompt, "")) : el("div", { class: "prompt" }, step.prompt));
  }
  if (step.audio) promptRow.append(audioButton(step.audio, "Ouvir de novo"));
  block.append(promptRow);
  if (step.hint) block.append(el("div", { class: "hint" }, step.hint));
  return block;
}

async function submitAnswer(step, answer, extra = {}) {
  const s = state.session;
  const result = await api("/api/answer", { body: { token: step.token, answer, mode: s.mode, ...extra } });
  s.answered += 1;
  if (!s.results.has(step.item_id)) s.results.set(step.item_id, { step, first: result.score, label: step.prompt || step.front || step.audio || step.instruction || "" });
  const noRetry = ["produce", "shadow", "tf", "flashcard"].includes(step.exercise) || step.kind === "structure";
  if (result.score < 1 && !s.retried.has(step.item_id) && !noRetry) {
    s.retried.add(step.item_id);
    api(`/api/retry?item_id=${encodeURIComponent(step.item_id)}&theme=${step.theme_id}&variant=${step.exercise}`)
      .then((again) => {
        if (!again || !again.token || state.session !== s) return;
        const last = s.steps[s.steps.length - 1];
        const end = s.steps.length - (last && last.type === "part_end" ? 1 : 0);
        s.steps.splice(Math.max(s.index + 1, Math.min(s.index + 4, end)), 0, again);
        updateProgress();
      })
      .catch(() => {});
  }
  return result;
}

function feedbackBox(result, step) {
  const cls = result.correct ? "feedback" : result.partial ? "feedback partial" : "feedback wrong";
  const title = result.correct ? "Certo." : result.partial ? "Quase." : "Não foi desta vez.";
  const box = el("div", { class: cls, role: "status" }, el("strong", {}, title));
  if (result.words) {
    box.append(el("p", { class: "dictation-words" }, ...result.words.map((w) => el("span", { class: w.ok ? "w-ok" : "w-bad" }, w.w)), " "));
  } else if (!result.correct && result.answer) {
    box.append(el("p", {}, "Resposta: ", /[а-яё]/i.test(result.answer) ? ruText(result.answer) : result.answer));
  }
  if (result.note) box.append(el("p", {}, result.note));
  if (result.transcript) box.append(el("p", {}, "Áudio: ", ruText(result.transcript)));
  if (result.full && result.full !== result.answer) box.append(el("p", {}, `Significados: ${result.full}`));
  if (result.translation) box.append(el("p", {}, `Tradução: ${result.translation}`));
  if (result.explanation) box.append(el("p", {}, ruText(result.explanation, "")));
  return box;
}

function continueRow() {
  const button = el("button", { class: "btn primary", type: "button", "data-autofocus": true, onclick: next }, "Continuar");
  setTimeout(() => button.focus(), 0);
  return el("div", { class: "next-row" }, button);
}

function renderChoice(step) {
  const panel = el("div", { class: "panel" }, promptBlock(step));
  const options = el("div", { class: "options" });
  let locked = false;
  const buttons = step.options.map((option, index) => {
    const button = el("button", { class: `option${step.ru_options ? " ru-text" : ""}`, type: "button" },
      el("span", { class: "key" }, index + 1), el("span", {}, option));
    button.addEventListener("click", async () => {
      if (locked) return;
      locked = true;
      buttons.forEach((b) => { b.disabled = true; });
      try {
        const result = await submitAnswer(step, option);
        buttons.forEach((b, i) => {
          if (step.options[i] === result.answer || (result.correct && i === index)) b.classList.add("correct");
        });
        if (!result.correct) button.classList.add("wrong");
        panel.append(feedbackBox(result, step), continueRow());
      } catch (error) {
        panel.append(el("div", { class: "feedback wrong" }, el("strong", {}, error.message)), continueRow());
      }
    });
    return button;
  });
  options.append(...buttons);
  panel.append(options);
  panel.dataset.keys = "options";
  return panel;
}

function renderInput(step) {
  const input = step.long
    ? el("textarea", { rows: 3, spellcheck: "false", lang: "ru", "aria-label": "Resposta em russo", "data-autofocus": true, class: "dictation-area" })
    : el("input", { type: "text", autocomplete: "off", spellcheck: "false", lang: "ru", "aria-label": "Resposta em russo", "data-autofocus": true });
  const check = el("button", { class: "btn primary", type: "button" }, "Verificar");
  const panel = el("div", { class: "panel" }, promptBlock(step), el("div", { class: "typed" }, input, check),
    el("p", { class: "hint" }, "Dica: use o teclado russo do Windows (Win + Espaço alterna o idioma)."));
  const submit = async () => {
    if (!input.value.trim() || check.disabled) return;
    check.disabled = true;
    input.disabled = true;
    const result = await submitAnswer(step, input.value.trim());
    panel.append(feedbackBox(result, step), continueRow());
  };
  check.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); submit(); } });
  return panel;
}

function renderFlashcard(step) {
  const panel = el("div", { class: "panel" }, promptBlock({ ...step, prompt: "" }), el("div", { class: "prompt ru" }, ruText(step.front, "")));
  const reveal = el("button", { class: "btn primary", type: "button", "data-autofocus": true }, "Mostrar resposta");
  reveal.addEventListener("click", () => {
    reveal.remove();
    const rate = async (rating) => {
      rating_row.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      await submitAnswer(step, "", { rating });
      panel.append(continueRow());
    };
    const rating_row = el("div", { class: "rating" },
      el("button", { class: "btn", type: "button", onclick: () => rate(1) }, "Não lembrei"),
      el("button", { class: "btn", type: "button", onclick: () => rate(2) }, "Lembrei em parte"),
      el("button", { class: "btn primary", type: "button", onclick: () => rate(3) }, "Lembrei"));
    panel.append(el("div", { class: "feedback" }, el("p", {}, ruText(step.back, "")), step.explanation ? el("p", {}, ruText(step.explanation, "")) : null), rating_row);
    rating_row.querySelector("button.primary").focus();
  });
  panel.append(el("div", { class: "next-row" }, reveal));
  return panel;
}

function renderOrder(step) {
  const line = el("div", { class: "order-line", "aria-label": "Sua frase" });
  const pool = el("div", { class: "order-pool" });
  const chosen = [];
  const check = el("button", { class: "btn primary", type: "button", disabled: true }, "Verificar");
  const refresh = () => { check.disabled = chosen.length !== step.tokens.length; };
  step.tokens.forEach((token) => {
    const chip = el("button", { class: "chip", type: "button" }, token);
    chip.addEventListener("click", () => {
      if (check.dataset.done) return;
      if (chip.parentElement === pool) { line.append(chip); chosen.push(chip); }
      else { pool.append(chip); chosen.splice(chosen.indexOf(chip), 1); }
      refresh();
    });
    pool.append(chip);
  });
  const panel = el("div", { class: "panel" }, promptBlock(step), line, pool);
  check.addEventListener("click", async () => {
    check.dataset.done = "1";
    check.disabled = true;
    const result = await submitAnswer(step, chosen.map((c) => c.textContent).join(" "));
    panel.append(feedbackBox(result, step), continueRow());
  });
  panel.append(el("div", { class: "next-row" }, check));
  return panel;
}

function renderSummary() {
  const s = state.session;
  const results = [...s.results.values()];
  const right = results.filter((r) => r.first >= 1).length;
  const missed = results.filter((r) => r.first < 1);
  const box = el("div", { class: "panel summary" },
    el("h2", {}, s.mode === "study" ? "Sessão concluída" : "Revisão concluída"),
    el("p", { class: "hint" }, "Os itens errados voltam em cerca de dez minutos; os acertos voltam em intervalos cada vez maiores."),
    el("div", { class: "summary-stats" },
      el("div", {}, el("b", {}, `${percent(right, results.length)}%`), el("span", {}, "de acerto na primeira tentativa")),
      el("div", {}, el("b", {}, s.introduced), el("span", {}, "itens novos")),
      el("div", {}, el("b", {}, s.answered), el("span", {}, "respostas"))));
  if (missed.length) {
    box.append(el("h3", {}, "Para prestar atenção"), el("div", { class: "summary-list" },
      ...missed.slice(0, 12).map((r) => el("div", {}, ruText(r.label, ""), el("small", { class: "hint" }, kindLabel(r.step))))));
  }
  box.append(el("div", { class: "next-row" },
    el("button", { class: "btn", type: "button", onclick: endSession }, "Voltar aos temas"),
    el("button", { class: "btn primary", type: "button", "data-autofocus": true, onclick: () => startSession(s.theme.id, s.mode, true) },
      s.mode === "study" ? "Mais palavras novas" : "Revisar mais")));
  return box;
}

document.addEventListener("keydown", (event) => {
  if (!$("#modal").hidden && event.key === "Escape") { closeModal(); return; }
  if (!state.session || $("#view-session").hidden) return;
  if (event.target.tagName === "INPUT") return;
  const panel = $("#stage .panel");
  if (!panel) return;
  if (/^[1-4]$/.test(event.key) && panel.dataset.keys === "options") {
    const option = panel.querySelectorAll(".option")[Number(event.key) - 1];
    if (option && !option.disabled) option.click();
  }
});

// ------------------------------------------------------------------ atualização
async function checkUpdate() {
  try {
    const info = await api("/api/update/check");
    if (!info.available) return;
    const banner = $("#update-banner");
    const button = el("button", { class: "btn primary", type: "button" }, "Atualizar agora");
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Baixando…";
      try {
        await api("/api/update/apply", { body: {} });
        const poll = setInterval(async () => {
          const status = await api("/api/update/status").catch(() => null);
          if (!status) return;
          if (status.phase === "error") { clearInterval(poll); button.textContent = "Falhou"; toast(status.error || "A atualização falhou."); }
          else if (status.total) button.textContent = `Baixando… ${percent(status.done, status.total)}%`;
        }, 800);
      } catch (error) {
        toast(error.message);
        button.disabled = false;
        button.textContent = "Atualizar agora";
      }
    });
    banner.replaceChildren(el("span", {}, `Nova versão disponível: ${info.latest}.`), button);
    banner.hidden = false;
  } catch (_) { /* sem internet: segue sem aviso */ }
}

boot();
