"use strict";

/* LinguaLab · Français — página própria do curso de francês (B1 → C1).
   Trilha gramatical, eixos temáticos, sprint de verbos e caderno de erros.
   Princípio: errar não custa nada. Cada erro abre uma escada de ajuda (sinal → pista → resposta),
   o item volta algumas telas depois e, quando você o recupera, ganha XP extra. O XP nunca diminui. */

const fr = { data: null, tab: "trilha", session: null, loading: null };
const FR_TABS = [["trilha", "Trilha"], ["eixos", "Eixos temáticos"], ["verbos", "Verbos"], ["caderno", "Caderno de erros"], ["conquistas", "Conquistas"]];
const FR_ACCENTS = ["é", "è", "ê", "à", "â", "ç", "ù", "û", "î", "ï", "ô", "ë", "œ", "«", "»"];
const FR_CHOICE = new Set(["mc", "register", "gender", "fr_pt", "pt_fr", "listen"]);
const FR_TYPED = new Set(["gap", "type", "transform", "dict"]);
const FR_GOALS = [[50, "Leve · 50 XP (≈ 5 min)"], [100, "Regular · 100 XP (≈ 10 min)"], [150, "Firme · 150 XP (≈ 15 min)"], [250, "Intenso · 250 XP (≈ 25 min)"], [400, "Maratona · 400 XP (≈ 40 min)"]];
const FR_DEFAULT_TENSES = ["pres", "pc", "imp", "fut", "cond", "subj"];

// ------------------------------------------------------------------ utilidades
function frStore(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch (_) { /* sem armazenamento: vale só nesta janela */ }
  return null;
}

let frAudio = null;
/** Língua do áudio: a do curso da sessão aberta ou, fora de sessão, a do curso na tela. */
function frLang() {
  return fr.session?.course?.lang || (currentCourse() === "kz" ? "kk" : "fr");
}

function frPlay(text, button = null, voice = "", src = "") {
  if (!text && !src) return null;
  stopAllAudio();
  if (frAudio) frAudio.pause();
  const lang = frLang();
  const audio = new Audio(src || `/api/tts?lang=${lang}${voice ? `&voice=${voice}` : ""}&text=${encodeURIComponent(text)}`);
  frAudio = audio;
  button?.classList.add("playing");
  audio.addEventListener("ended", () => button?.classList.remove("playing"));
  audio.addEventListener("pause", () => button?.classList.remove("playing"));
  audio.addEventListener("error", () => {
    button?.classList.remove("playing");
    toast(lang === "kk" ? "Áudio indisponível agora. As vozes cazaques vêm do Edge: verifique a internet."
      : "Áudio indisponível agora. Verifique a internet ou instale a voz francesa do Windows.");
  });
  audio.play().catch(() => button?.classList.remove("playing"));
  return audio;
}

function frAudioButton(text, label = "Ouvir", voice = "") {
  const button = el("button", { class: "audio-btn", type: "button", "aria-label": label, title: label }, svgIcon("M8 5v14l11-7z"));
  button.addEventListener("click", (event) => { event.stopPropagation(); frPlay(text, button, voice); });
  return button;
}

/** Efeitos sonoros curtos (Web Audio); desligáveis no cabeçalho. */
let frAudioCtx = null;
function frSfx(kind) {
  if (frStore("fr-sfx") === "off") return;
  try {
    frAudioCtx = frAudioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = { ok: [660, 880], bad: [300], level: [523, 659, 784, 1047], tick: [990] }[kind] || [440];
    notes.forEach((freq, i) => {
      const osc = frAudioCtx.createOscillator();
      const gain = frAudioCtx.createGain();
      osc.type = kind === "bad" ? "triangle" : "sine";
      osc.frequency.value = freq;
      const start = frAudioCtx.currentTime + i * 0.09;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(kind === "bad" ? 0.06 : 0.09, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.22);
      osc.connect(gain).connect(frAudioCtx.destination);
      osc.start(start);
      osc.stop(start + 0.25);
    });
  } catch (_) { /* sem áudio: segue em silêncio */ }
}

function frConfetti() {
  const box = el("div", { class: "fr-confetti", "aria-hidden": "true" });
  const colors = ["#2d4fa3", "#c07a3a", "#4a8a4a", "#b06a5a", "#e2b55b", "#6a5aa0"];
  for (let i = 0; i < 46; i += 1) {
    box.append(el("i", { style: { left: `${Math.random() * 100}%`, background: colors[i % colors.length], animationDelay: `${Math.random() * 0.4}s`, transform: `rotate(${Math.random() * 360}deg)` } }));
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 2600);
}

function frFloatXp(anchor, text) {
  if (!anchor) return;
  const rect = anchor.getBoundingClientRect();
  const node = el("div", { class: "fr-float-xp", style: { left: `${rect.left + rect.width / 2}px`, top: `${rect.top}px` } }, text);
  document.body.append(node);
  setTimeout(() => node.remove(), 1300);
}

function goalRing(value, goal, size = 92) {
  const ns = "http://www.w3.org/2000/svg";
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;
  const ratio = Math.min(1, goal ? value / goal : 0);
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("class", `fr-ring${ratio >= 1 ? " done" : ""}`);
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  for (const [cls, dash] of [["track", circumference], ["value", circumference * ratio]]) {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", size / 2);
    c.setAttribute("cy", size / 2);
    c.setAttribute("r", radius);
    c.setAttribute("class", cls);
    c.setAttribute("stroke-dasharray", `${dash} ${circumference}`);
    svg.append(c);
  }
  return el("div", { class: "fr-ring-wrap", style: { width: `${size}px`, height: `${size}px` } }, svg,
    el("div", { class: "fr-ring-label" }, el("b", {}, number.format(value)), el("small", {}, `de ${goal} XP`)));
}

function stars(count, total = 3) {
  return el("span", { class: "fr-stars", "aria-label": `${count} de ${total} estrelas` },
    ...Array.from({ length: total }, (_, i) => el("i", { class: i < count ? "on" : "" }, "★")));
}

function stageDot(stage) {
  const cls = stage === null || stage === undefined ? "" : stage >= 4 ? " mastered" : " seen";
  const title = stage === null || stage === undefined ? "ainda não estudado" : stage >= 4 ? "dominado" : `estágio ${stage} de 8`;
  return el("span", { class: `status-dot${cls}`, title });
}

// ------------------------------------------------------------------ troca de curso
function currentCourse() {
  const saved = frStore("lingualab-course");
  return saved === "fr" || saved === "kz" ? saved : "ru";
}

const COURSE_LOOK = {
  ru: { mark: "Я", name: "Русский", title: "LinguaLab · Русский" },
  fr: { mark: "Fr", name: "Français", title: "LinguaLab · Français" },
  kz: { mark: "Қз", name: "Қазақша", title: "LinguaLab · Қазақша" },
};

function setCourse(course) {
  frStore("lingualab-course", course);
  document.documentElement.dataset.course = course;
  document.querySelectorAll("#course-switch button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.course === course)));
  const look = COURSE_LOOK[course] || COURSE_LOOK.ru;
  $(".brand-mark").textContent = look.mark;
  $(".brand-name").replaceChildren("LinguaLab ", el("span", { class: "ru" }, look.name));
  document.title = look.title;
  $("#search-form").hidden = course !== "ru";
  $("#topbar-stats").hidden = course !== "ru";
  $("#fr-topbar-stats").hidden = course !== "fr";
  if ($("#kz-topbar-stats")) $("#kz-topbar-stats").hidden = course !== "kz";
  // A tela de sessão é compartilhada por francês e cazaque; só aparece no curso dono da sessão.
  const ownSession = Boolean(fr.session) && (fr.session.course?.id || "fr") === course;
  $("#view-fr-session").hidden = !ownSession;
  $("#view-fr").hidden = course !== "fr" || ownSession;
  if ($("#view-kz")) $("#view-kz").hidden = course !== "kz" || ownSession;
  const russianSession = typeof state !== "undefined" && state.session;
  $("#view-gallery").hidden = course !== "ru" || Boolean(russianSession);
  $("#view-session").hidden = course !== "ru" || !russianSession;
  if (course === "fr" && !fr.data) frLoad();
  if (course === "kz" && typeof kzLoad === "function") kzLoad();
}

$("#course-switch").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-course]");
  if (button) setCourse(button.dataset.course);
});

// O logotipo volta ao início do curso que está aberto.
$("#home-button").addEventListener("click", (event) => {
  if (currentCourse() === "ru") return;
  event.stopImmediatePropagation();
  if (fr.session) frEndSession();
  else window.scrollTo({ top: 0, behavior: "smooth" });
}, true);

// ------------------------------------------------------------------ dados e página inicial
async function frLoad() {
  if (fr.loading) return fr.loading;
  fr.loading = (async () => {
    try {
      fr.data = await api("/api/fr/overview");
      renderFrHome();
    } catch (error) {
      $("#fr-panel").replaceChildren(el("p", { class: "loading" }, `Não foi possível carregar o curso de francês: ${error.message}`));
    } finally {
      fr.loading = null;
    }
  })();
  return fr.loading;
}

function renderFrTopbar() {
  const p = fr.data.profile;
  const parts = [
    el("span", {}, el("b", {}, `Nv. ${p.level}`), ` ${p.title}`),
    el("span", { class: p.xp_today >= p.goal ? "goal-done" : "" }, el("b", {}, number.format(p.xp_today)), `/${p.goal} XP hoje`),
  ];
  if (p.streak) parts.push(el("span", {}, "🔥 ", el("b", {}, p.streak), p.streak === 1 ? " dia" : " dias"));
  parts.push(el("span", {}, el("b", {}, number.format(p.due)), " para revisar"));
  $("#fr-topbar-stats").replaceChildren(...parts);
}

function nextUnit() {
  for (const phase of fr.data.phases) {
    const unit = phase.units.find((u) => !u.extra && u.seen < u.total);
    if (unit) return unit;
  }
  return null;
}

function renderFrHome() {
  if (!fr.data) return;
  renderFrTopbar();
  const p = fr.data.profile;
  const sfxOn = frStore("fr-sfx") !== "off";
  const levelBar = el("div", { class: "fr-xpbar" }, el("span", { style: { width: `${percent(p.into, p.span)}%` } }));
  const next = nextUnit();
  const actions = el("div", { class: "fr-actions" });
  const review = el("button", { class: `btn${p.due ? " primary" : ""}`, type: "button", disabled: p.seen === 0, onclick: () => frStart("/api/fr/session?kind=review") },
    p.due ? `Revisar agora` : "Revisão extra", el("small", {}, p.due ? `${number.format(p.due)} itens esperando` : p.seen ? "reforçar o que já viu" : "nada estudado ainda"));
  if (next) {
    actions.append(el("button", { class: `btn${p.due ? "" : " primary"}`, type: "button", onclick: () => frStart(`/api/fr/session?kind=unit&id=${next.id}&mode=learn`) },
      `Continuar a trilha`, el("small", {}, `${next.n}. ${next.title}`)));
  }
  actions.append(review,
    el("button", { class: "btn", type: "button", onclick: () => frStartSprint() }, "Sprint de verbos", el("small", {}, fr.data.sprint_best ? `recorde: ${fr.data.sprint_best} formas` : "90 segundos contra o relógio")),
    el("button", { class: "btn", type: "button", disabled: !fr.data.notebook.open, onclick: () => frStart("/api/fr/session?kind=notebook") }, "Treinar meus erros",
      el("small", {}, fr.data.notebook.open ? `${fr.data.notebook.open} itens para recuperar` : "caderno em dia")));

  const intro = p.seen === 0
    ? el("div", { class: "fr-callout" },
      el("strong", {}, "Comece pelo diagnóstico (≈ 15 min). "),
      "Uma pergunta de cada unidade das fases 1 e 2: o resultado mostra onde concentrar o estudo e o que você já pode pular.",
      el("button", { class: "btn primary small", type: "button", onclick: () => frStart("/api/fr/session?kind=diagnostic") }, "Fazer o diagnóstico"))
    : null;

  $("#fr-hero").replaceChildren(
    el("div", { class: "fr-hero-text" },
      el("h1", {}, "Français ", el("span", { class: "fr-level-tag" }, "B1 → C1")),
      el("p", {}, "Errar não custa nada: cada erro vira uma pista, volta mais adiante e, quando você o recupera, rende XP extra. Exigente, mas sem castigo."),
      el("div", { class: "fr-level" },
        el("div", { class: "fr-level-badge" }, el("b", {}, p.level), el("small", {}, "nível")),
        el("div", { class: "fr-level-info" },
          el("strong", {}, p.title),
          levelBar,
          el("small", {}, `${number.format(p.into)} / ${number.format(p.span)} XP até o próximo nível · ${number.format(p.xp_total)} XP no total`))),
      actions, intro),
    el("div", { class: "fr-hero-side" },
      el("div", { class: "fr-goal" }, goalRing(p.xp_today, p.goal),
        el("div", {}, el("strong", {}, p.xp_today >= p.goal ? "Meta cumprida!" : "Meta do dia"),
          el("button", { class: "text-button", type: "button", onclick: frGoalModal }, "mudar meta"))),
      el("div", { class: "fr-mini-stats" },
        el("div", {}, el("b", {}, `🔥 ${p.streak}`), el("small", {}, p.streak === 1 ? "dia seguido" : "dias seguidos")),
        el("div", {}, el("b", {}, number.format(p.mastered)), el("small", {}, "dominados")),
        el("div", {}, el("b", {}, number.format(p.recovered)), el("small", {}, "erros recuperados"))),
      el("button", { class: "text-button", type: "button", onclick: (e) => {
        frStore("fr-sfx", sfxOn ? "off" : "on");
        e.currentTarget.textContent = sfxOn ? "🔇 sons desligados" : "🔊 sons ligados";
        renderFrHome();
      } }, sfxOn ? "🔊 sons ligados" : "🔇 sons desligados")));

  $("#fr-tabs").replaceChildren(...FR_TABS.map(([id, label]) =>
    el("button", { type: "button", "aria-pressed": String(fr.tab === id), onclick: () => { fr.tab = id; renderFrHome(); } }, label)));
  renderFrPanel();
}

function renderFrPanel() {
  const panel = $("#fr-panel");
  if (fr.tab === "trilha") panel.replaceChildren(renderTrail());
  else if (fr.tab === "eixos") panel.replaceChildren(renderThemes());
  else if (fr.tab === "verbos") panel.replaceChildren(renderVerbs());
  else if (fr.tab === "caderno") { panel.replaceChildren(el("p", { class: "loading" }, "Abrindo o caderno…")); renderNotebook().then((node) => panel.replaceChildren(node)); }
  else panel.replaceChildren(renderAchievements());
}

function frGoalModal() {
  const select = el("select", {}, ...FR_GOALS.map(([value, label]) => el("option", { value, selected: value === fr.data.profile.goal }, label)));
  openModal(el("div", {},
    el("h2", { id: "modal-title" }, "Meta diária"),
    el("p", { class: "hint" }, "A meta conta XP, não acertos: tentar já rende pontos, e a sequência de dias continua quando você cumpre ao menos um terço da meta."),
    el("div", { class: "settings-grid" }, el("label", {}, "XP por dia", select)),
    el("div", { class: "next-row" }, el("button", { class: "btn primary", type: "button", onclick: async () => {
      fr.data.profile = await api("/api/fr/goal", { body: { goal: Number(select.value) } });
      closeModal();
      renderFrHome();
    } }, "Salvar"))));
}

// ------------------------------------------------------------------ trilha
function renderTrail() {
  const wrap = el("div", { class: "fr-trail" });
  for (const phase of fr.data.phases) {
    const seen = phase.units.reduce((a, u) => a + u.seen, 0);
    const total = phase.units.reduce((a, u) => a + u.total, 0);
    const mastered = phase.units.reduce((a, u) => a + u.mastered, 0);
    wrap.append(el("section", { class: "fr-phase" },
      el("header", {},
        el("div", {}, el("span", { class: "fr-phase-n" }, `Fase ${phase.n}`), el("h2", {}, phase.title), el("span", { class: "fr-level-tag" }, phase.level)),
        el("p", {}, phase.goal),
        el("div", { class: "fr-phase-meter" }, meter(seen, mastered, total), el("small", {}, `${percent(seen, total)}% visto · ${percent(mastered, total)}% dominado`))),
      el("div", { class: "fr-units" }, ...phase.units.map(unitNode))));
  }
  return wrap;
}

function unitNode(unit) {
  const done = unit.total && unit.seen >= unit.total;
  return el("button", { class: `fr-unit${done ? " done" : ""}${unit.extra ? " extra" : ""}`, type: "button", onclick: () => openUnit(unit) },
    el("span", { class: "fr-unit-n" }, unit.extra ? "★" : unit.n),
    el("span", { class: "fr-unit-title" }, unit.title.replace(/^Extra · /, "")),
    el("span", { class: "fr-unit-tags" }, unit.extra ? el("span", { class: "pill" }, "extra") : null,
      unit.prio >= 3 ? el("span", { class: "pill key" }, "essencial") : null, stars(unit.stars)),
    meter(unit.seen, unit.mastered, unit.total),
    el("span", { class: "card-foot" }, el("span", {}, `${unit.seen}/${unit.total}`),
      unit.due ? el("span", { class: "due" }, `${unit.due} para revisar`) : el("span", {}, done ? "concluída" : unit.seen ? "em andamento" : "nova")));
}

function renderRules(rules) {
  return el("div", { class: "fr-rules" }, ...(rules || []).map((rule) => el("section", { class: "fr-rule" },
    el("h3", {}, rule.title),
    el("ul", {}, ...(rule.points || []).map((p) => el("li", {}, p))),
    rule.ex?.length ? el("div", { class: "examples" }, ...rule.ex.map(([f, pt]) => el("div", { class: "example-row" }, frAudioButton(f), el("div", {}, el("span", { class: "fr-text" }, f), el("small", {}, pt))))) : null,
    rule.trap ? el("p", { class: "trap" }, "Armadilha para lusófonos: ", rule.trap) : null)));
}

async function openUnit(unit) {
  const detail = await api(`/api/fr/unit?id=${encodeURIComponent(unit.id)}`);
  const theme = fr.data.themes.find((t) => t.id === detail.theme);
  const learn = el("button", { class: "btn primary", type: "button", onclick: () => { closeModal(); frStart(`/api/fr/session?kind=unit&id=${unit.id}&mode=learn`); } },
    unit.seen < unit.total ? (unit.seen ? "Continuar a unidade" : "Aprender") : "Praticar de novo", el("small", {}, `${unit.total - unit.seen} exercícios novos`));
  const challenge = el("button", { class: "btn", type: "button", disabled: unit.seen === 0, onclick: () => { closeModal(); frStart(`/api/fr/session?kind=unit&id=${unit.id}&mode=challenge`); } },
    "Desafio", el("small", {}, unit.seen ? `todos os ${unit.total} itens, sem aula · melhor: ${"★".repeat(unit.stars) || "nenhuma estrela"}` : "libera depois do primeiro estudo"));
  const review = el("button", { class: "btn", type: "button", disabled: unit.seen === 0, onclick: () => { closeModal(); frStart(`/api/fr/session?kind=review&scope=unit:${unit.id}`); } },
    "Revisar a unidade", el("small", {}, unit.due ? `${unit.due} para hoje` : "reforço"));
  openModal(el("div", { class: "fr-unit-modal" },
    el("span", { class: "kind-tag" }, unit.extra ? "Unidade extra" : `Fase ${detail.phase} · unidade ${detail.n}`),
    el("h2", { id: "modal-title" }, detail.title),
    el("p", { class: "hint" }, detail.goal),
    el("div", { class: "fr-modal-actions" }, learn, challenge, review),
    theme ? el("p", { class: "hint" }, "Eixo ligado: ", el("button", { class: "text-button", type: "button", onclick: () => openTheme(theme.id) }, `${theme.fr} · ${theme.name}`)) : null,
    el("h3", {}, "A regra"), renderRules(detail.rules)));
}

// ------------------------------------------------------------------ eixos
function renderThemes() {
  return el("div", {},
    el("p", { class: "hint fr-panel-intro" }, "Cada eixo reúne o vocabulário de um campo da vida, com artigo, exemplo e áudio. As palavras novas passam por reconhecimento, gênero, escuta e escrita; os eixos marcados DELF são os mais cobrados no exame."),
    el("div", { class: "fr-themes" }, ...fr.data.themes.map((theme) =>
      el("button", { class: "card fr-theme", type: "button", style: { "--tab": theme.color }, onclick: () => openTheme(theme.id) },
        el("span", { class: "card-ru fr-text" }, theme.fr),
        el("span", { class: "card-pt" }, theme.name, theme.delf ? el("span", { class: "pill key" }, "DELF") : null),
        el("span", { class: "card-preview fr-text" }, theme.preview.join(", ")),
        meter(theme.seen, theme.mastered, theme.total),
        el("span", { class: "card-foot" }, el("span", {}, `${theme.seen} de ${theme.total}`),
          theme.due ? el("span", { class: "due" }, `${theme.due} para revisar`) : el("span", {}, `${percent(theme.seen, theme.total)}%`))))));
}

async function openTheme(themeId) {
  const theme = await api(`/api/fr/theme?id=${encodeURIComponent(themeId)}`);
  const summary = fr.data.themes.find((t) => t.id === themeId);
  const fresh = theme.words.filter((w) => w.stage === null).length;
  const units = fr.data.phases.flatMap((p) => p.units).filter((u) => (theme.units || []).includes(u.n));
  openModal(el("div", { style: { "--tab": theme.color } },
    el("span", { class: "kind-tag" }, "Eixo temático"),
    el("h2", { id: "modal-title", class: "fr-text" }, theme.fr),
    el("p", {}, theme.name, " · ", theme.desc),
    el("div", { class: "fr-modal-actions" },
      el("button", { class: "btn primary", type: "button", disabled: fresh === 0, onclick: () => { closeModal(); frStart(`/api/fr/session?kind=theme&id=${themeId}`); } },
        "Palavras novas", el("small", {}, `${fresh} ainda não vistas`)),
      el("button", { class: "btn", type: "button", disabled: !summary?.seen, onclick: () => { closeModal(); frStart(`/api/fr/session?kind=review&scope=theme:${themeId}`); } },
        "Revisar o eixo", el("small", {}, summary?.due ? `${summary.due} para hoje` : "reforço"))),
    units.length ? el("p", { class: "hint" }, "Gramática ligada: ", ...units.map((u) => el("button", { class: "text-button fr-chip-link", type: "button", onclick: () => openUnit(u) }, `${u.n}. ${u.title}`))) : null,
    el("div", { class: "item-list" }, ...theme.words.map((w) => el("div", { class: "item-row" },
      stageDot(w.stage), el("span", { class: "fr-text" }, w.fr, " ", frAudioButton(w.fr)), el("span", {}, w.pt), el("small", {}, [w.lv, w.reg].filter(Boolean).join(" · ")))))));
}

// ------------------------------------------------------------------ verbos
function sprintTenses() {
  const saved = (frStore("fr-sprint-tenses") || "").split(",").filter((t) => fr.data.tenses[t]);
  return saved.length ? saved : FR_DEFAULT_TENSES;
}

function sprintVerbs(mode) {
  const verbs = fr.data.verbs;
  if (mode === "core") return verbs.slice(0, 20).map((v) => v.inf);
  if (mode === "weak") return [...verbs].sort((a, b) => (a.mastered - b.mastered) || (a.seen - b.seen)).slice(0, 15).map((v) => v.inf);
  return verbs.map((v) => v.inf);
}

function frStartSprint() {
  const mode = frStore("fr-sprint-verbs") || "all";
  frStart(`/api/fr/session?kind=sprint&tenses=${sprintTenses().join(",")}&verbs=${sprintVerbs(mode).join(",")}`);
}

function renderVerbs() {
  const chosen = new Set(sprintTenses());
  const tenseChips = el("div", { class: "fr-chips" }, ...Object.entries(fr.data.tenses).map(([id, label]) =>
    el("button", { type: "button", class: "chip", "aria-pressed": String(chosen.has(id)), onclick: (e) => {
      if (chosen.has(id) && chosen.size > 1) chosen.delete(id); else chosen.add(id);
      e.currentTarget.setAttribute("aria-pressed", String(chosen.has(id)));
      frStore("fr-sprint-tenses", [...chosen].join(","));
    } }, label)));
  const verbSet = el("select", {}, ...[["all", "Todos os 63 verbos"], ["core", "Os 20 mais frequentes"], ["weak", "Os 15 que eu menos domino"]].map(([value, label]) =>
    el("option", { value, selected: value === (frStore("fr-sprint-verbs") || "all") }, label)));
  verbSet.addEventListener("change", () => frStore("fr-sprint-verbs", verbSet.value));
  const tenseIds = Object.keys(fr.data.tenses);
  return el("div", {},
    el("section", { class: "fr-sprint-card" },
      el("div", {},
        el("h2", {}, "Sprint de verbos"),
        el("p", { class: "hint" }, "90 segundos, uma forma por vez: digite só o verbo (com o pronome reflexivo e o auxiliar quando houver) e aperte Enter. Cada forma entra na revisão espaçada; a meta é responder em menos de 2 segundos."),
        el("p", { class: "fr-record" }, fr.data.sprint_best ? `Recorde: ${fr.data.sprint_best} formas certas` : "Ainda sem recorde.")),
      el("div", { class: "fr-sprint-config" },
        el("strong", {}, "Tempos"), tenseChips,
        el("label", { class: "fr-inline-label" }, "Verbos ", verbSet),
        el("button", { class: "btn primary", type: "button", onclick: frStartSprint }, "Começar o sprint"))),
    el("div", { class: "fr-verb-table" },
      el("div", { class: "fr-verb-row head" }, el("span", {}, "Verbo"), el("span", {}, "Família"),
        el("span", { class: "fr-verb-dots" }, ...tenseIds.map((t) => el("abbr", { title: fr.data.tenses[t] }, t)))),
      ...fr.data.verbs.map((verb) => el("button", { type: "button", class: "fr-verb-row", onclick: () => openVerb(verb.inf) },
        el("span", {}, el("b", { class: "fr-text" }, verb.inf), el("small", {}, verb.pt)),
        el("span", { class: "hint" }, verb.family),
        el("span", { class: "fr-verb-dots" }, ...tenseIds.map((t) => stageDot(verb.tenses[t])))))));
}

async function openVerb(inf) {
  const verb = await api(`/api/fr/verb?inf=${encodeURIComponent(inf)}`);
  const cards = Object.entries(verb.table).map(([tense, forms]) => el("div", { class: "fr-conj-card" },
    el("h4", {}, verb.tenses[tense], " ", stageDot(verb.states[tense]), " ", frAudioButton(forms.join(", "), `Ouvir ${verb.tenses[tense]}`)),
    el("ol", {}, ...forms.map((f) => el("li", { class: "fr-text" }, f)))));
  openModal(el("div", {},
    el("span", { class: "kind-tag" }, verb.family),
    el("h2", { id: "modal-title", class: "fr-text" }, verb.inf, " ", frAudioButton(verb.inf)),
    el("p", {}, verb.pt, " · auxiliar ", el("b", {}, verb.aux), " · particípio ", el("b", { class: "fr-text" }, verb.pp)),
    verb.note ? el("p", { class: "trap" }, verb.note) : null,
    el("div", { class: "fr-conj-grid" }, ...cards)));
}

// ------------------------------------------------------------------ caderno de erros
async function renderNotebook() {
  const data = await api("/api/fr/notebook");
  const rows = Object.entries(data.categories).map(([code, label]) => ({ code, label, ...(data.stats[code] || { attempts: 0, ok: 0 }) }))
    .sort((a, b) => (b.attempts - b.ok) - (a.attempts - a.ok));
  const worst = rows.filter((r) => r.attempts > r.ok).slice(0, 5);
  return el("div", { class: "fr-notebook" },
    el("section", { class: "fr-callout" },
      el("strong", {}, data.open ? `${data.open} itens ainda por recuperar. ` : "Caderno em dia. "),
      "Cada erro entra aqui pela sua categoria. Recuperar um erro (acertar depois de ter errado) rende +5 XP.",
      el("button", { class: "btn primary small", type: "button", disabled: !data.open, onclick: () => frStart("/api/fr/session?kind=notebook") }, "Treinar tudo")),
    el("h3", {}, "Suas categorias nos últimos 30 dias"),
    worst.length ? el("p", { class: "hint" }, "Os seus cinco pontos fracos agora: ", worst.map((r) => r.label).join(" · "), ". Releia os seus textos procurando exatamente isso.") : null,
    el("div", { class: "fr-cat-list" }, ...rows.map((r) => {
      const missed = r.attempts - r.ok;
      return el("div", { class: `fr-cat${r.attempts ? "" : " empty"}` },
        el("span", { class: "fr-cat-code" }, r.code),
        el("span", { class: "fr-cat-label" }, r.label),
        el("span", { class: "fr-cat-bar" }, el("i", { style: { width: `${percent(r.ok, r.attempts)}%` } })),
        el("small", {}, r.attempts ? `${percent(r.ok, r.attempts)}% certas de primeira em ${r.attempts} · ${missed} ${missed === 1 ? "erro" : "erros"}` : "sem tentativas"),
        el("button", { class: "text-button", type: "button", disabled: !missed, onclick: () => frStart(`/api/fr/session?kind=notebook&category=${r.code}`) }, "treinar"));
    })),
    el("h3", {}, "Últimos erros"),
    data.recent.length ? el("div", { class: "fr-recent" }, ...data.recent.map((row) => el("div", { class: "fr-recent-row" },
      el("span", { class: "pill" }, row.category || "—"),
      el("div", {}, el("div", { class: "fr-text" }, row.prompt || row.label),
        el("small", {}, "você: ", el("span", { class: "w-bad" }, row.answer || "—"), " · certo: ", el("span", { class: "w-ok" }, row.expected)))))) : el("p", { class: "hint" }, "Nenhum erro registrado ainda."));
}

// ------------------------------------------------------------------ conquistas
function renderAchievements() {
  const list = fr.data.achievements;
  const done = list.filter((a) => a.done).length;
  return el("div", {},
    el("p", { class: "hint fr-panel-intro" }, `${done} de ${list.length} conquistas.`),
    el("div", { class: "fr-badges" }, ...list.map((a) => el("div", { class: `fr-badge${a.done ? " done" : ""}` },
      el("span", { class: "fr-badge-icon" }, a.done ? "🏅" : "🔒"),
      el("strong", {}, a.title), el("small", {}, a.desc)))));
}

// ------------------------------------------------------------------ sessão
/** Como a sessão conversa com o servidor e com a página do curso. O cazaque registra o seu em kazakh.js. */
const FR_COURSE = {
  id: "fr", api: "/api/fr", lang: "fr", keys: FR_ACCENTS, home: "#view-fr",
  data: () => fr.data, topbar: () => renderFrTopbar(), reload: () => frLoad(), renderers: {},
};

async function frStart(url, course = FR_COURSE) {
  let data;
  try {
    data = await api(url);
  } catch (error) {
    toast(error.message);
    return;
  }
  if (!data.steps?.length) {
    toast("Nada para estudar aqui agora.");
    return;
  }
  closeModal();
  fr.session = { url, course, mode: data.mode, title: data.title, unitId: data.unit_id || "", steps: data.steps, index: 0,
    results: new Map(), retried: new Set(), xp: 0, momentum: 0, bestMomentum: 0, recovered: 0, answered: 0,
    seconds: data.seconds || 0, sprintScore: 0, sprintMiss: [], startGoal: fr.data?.profile.xp_today ?? 0 };
  $(course.home).hidden = true;
  $("#view-fr-session").hidden = false;
  $("#fr-session-title").textContent = data.title;
  window.scrollTo(0, 0);
  if (data.mode === "sprint") renderSprint();
  else renderFrStep();
}

function frEndSession() {
  const s = fr.session;
  const course = s?.course || FR_COURSE;
  if (s?.timer) clearInterval(s.timer);
  fr.session = null;
  stopAllAudio();
  if (frAudio) frAudio.pause();
  $("#view-fr-session").hidden = true;
  $(course.home).hidden = false;
  course.reload();
}
$("#fr-session-close").addEventListener("click", frEndSession);

function frMeta() {
  const s = fr.session;
  const flames = el("span", { class: "fr-momentum", title: "Fôlego: sobe com acertos de primeira; um erro só tira um ponto." },
    ...Array.from({ length: 5 }, (_, i) => el("i", { class: i < s.momentum ? "on" : "" })));
  $("#fr-session-meta").replaceChildren(flames, el("span", { class: "fr-session-xp" }, `+${s.xp} XP`));
}

function frProgress() {
  const s = fr.session;
  $("#fr-session-bar").style.width = `${percent(s.index, s.steps.length)}%`;
  frMeta();
}

function renderFrStep() {
  const s = fr.session;
  frProgress();
  const stage = $("#fr-stage");
  if (s.index >= s.steps.length) {
    stage.replaceChildren(el("p", { class: "loading" }, "Fechando a sessão…"));
    renderFrSummary().then((node) => stage.replaceChildren(node));
    return;
  }
  const step = s.steps[s.index];
  let node;
  if (s.course.renderers?.[step.type]) node = s.course.renderers[step.type](step);
  else if (step.type === "rule") node = renderRuleStep(step);
  else if (step.type === "word") node = renderWordStep(step);
  else if (FR_CHOICE.has(step.t)) node = renderFrChoice(step);
  else if (FR_TYPED.has(step.t)) node = renderFrTyped(step);
  else if (step.t === "fix") node = renderFrFix(step);
  else if (step.t === "order") node = renderFrOrder(step);
  else if (step.t === "pairs") node = renderFrPairs(step);
  else node = el("div", { class: "panel" }, "Tipo de exercício desconhecido.", frContinueRow());
  stage.replaceChildren(node);
  (stage.querySelector("[data-autofocus]") || stage.querySelector("input, textarea, button.option"))?.focus();
  if ((step.t === "listen" || step.t === "dict") && step.audio) setTimeout(() => frPlay(step.audio, stage.querySelector(".fr-prompt-audio .audio-btn")), 300);
}

function frNext() {
  stopAllAudio();
  if (frAudio) frAudio.pause();
  fr.session.index += 1;
  renderFrStep();
}

function frContinueRow(label = "Continuar") {
  const button = el("button", { class: "btn primary fr-continue", type: "button", "data-autofocus": true, onclick: frNext }, label);
  setTimeout(() => button.focus(), 0);
  return el("div", { class: "next-row" }, button);
}

function stepHeader(step, instruction) {
  const tag = step.kind === "w" ? `Vocabulário · ${step.theme_name || ""}` : step.kind === "v" ? "Conjugação" : `${step.unit_title || ""}`;
  return el("div", {},
    el("div", { class: "fr-step-tags" }, el("span", { class: "kind-tag" }, tag),
      step.category_label ? el("span", { class: "pill" }, `${step.category} · ${step.category_label}`) : null,
      step.max_tries > 1 ? el("span", { class: "pill fr-tries" }, `${step.max_tries} tentativas`) : null),
    instruction ? el("div", { class: "instruction" }, instruction) : null);
}

/** Frase com a lacuna ___ destacada (ou com um campo no lugar dela). */
function sentence(text, input = null) {
  const parts = String(text || "").split("___");
  const node = el("div", { class: "prompt fr-text fr-sentence" });
  parts.forEach((part, index) => {
    node.append(part);
    if (index < parts.length - 1) node.append(input && index === 0 ? input : el("span", { class: "fr-blank" }, "____"));
  });
  return node;
}

function hintBox() {
  return el("div", { class: "fr-hint", hidden: true, role: "status" });
}

function showHint(box, result, step, counted = true) {
  box.hidden = false;
  const left = Math.max(0, (step.max_tries || 1) - (result.try || 0));
  const title = !counted ? "Onde está o erro?" : result.verdict === "accent" ? "Quase lá" : result.verdict === "empty" ? "Sua vez" : `Pista ${result.try || 1}`;
  box.replaceChildren(el("strong", {}, title), " ", result.hint || "",
    counted && left ? el("small", {}, ` · mais ${left} ${left === 1 ? "tentativa" : "tentativas"}`) : null);
  box.classList.remove("pulse");
  void box.offsetWidth;
  box.classList.add("pulse");
}

async function frSubmit(step, payload) {
  const s = fr.session;
  return api(`${s.course.api}/answer`, { body: { token: step.token, mode: s.mode, ...payload } });
}

/** Resposta final: XP, fôlego, item de volta mais adiante se errou, caixa de retorno. */
function frFinal(step, result, panel) {
  const s = fr.session;
  s.answered += 1;
  s.xp += (result.xp || 0) + (result.bonus || 0);
  if (!s.results.has(step.item_id)) s.results.set(step.item_id, { first: result.score, tries: result.try, label: step.q || step.p || step.audio || step.inf || "", step });
  if (result.correct && result.score >= 1) { s.momentum = Math.min(5, s.momentum + 1); frSfx("ok"); }
  else if (!result.correct) { s.momentum = Math.max(0, s.momentum - 1); frSfx("bad"); }
  else frSfx("ok");
  s.bestMomentum = Math.max(s.bestMomentum, s.momentum);
  if (result.recovered) { s.recovered += 1; frSfx("level"); }
  const data = s.course.data();
  if (data) {
    const before = data.profile.xp_today;
    data.profile.xp_today = result.xp_today ?? before;
    if (before < data.profile.goal && data.profile.xp_today >= data.profile.goal) {
      frConfetti();
      toast("Meta do dia cumprida! 🎉");
    }
    s.course.topbar();
  }
  frMeta();
  if (result.score < 1 && !s.retried.has(step.item_id) && s.mode !== "sprint" && s.mode !== "diagnostic") {
    s.retried.add(step.item_id);
    api(`${s.course.api}/again?item_id=${encodeURIComponent(step.item_id)}`).then((again) => {
      if (!again?.token || fr.session !== s) return;
      again.again = true;
      s.steps.splice(Math.min(s.index + 4, s.steps.length), 0, again);
      frProgress();
    }).catch(() => {});
  }
  const xpText = `+${result.xp}${result.bonus ? ` +${result.bonus}` : ""} XP`;
  frFloatXp(panel.querySelector(".fr-sentence, .prompt, .fr-tokens") || panel, xpText);
  panel.append(feedback(step, result), frContinueRow());
}

function feedback(step, result) {
  const helped = result.correct && result.score < 1;
  const cls = result.correct ? (helped ? "feedback partial" : "feedback") : "feedback wrong";
  const title = result.correct ? (helped ? "Certo, com ajuda." : ["Perfeito!", "Exato!", "Isso mesmo!", "Impecável!"][Math.floor(Math.random() * 4)]) : "Vamos fixar esta.";
  const box = el("div", { class: cls, role: "status" }, el("strong", {}, title),
    el("span", { class: "fr-xp-chip" }, `+${result.xp} XP`),
    result.recovered ? el("span", { class: "fr-xp-chip gold" }, `+${result.bonus} recuperado!`) : null);
  if (result.words) box.append(el("p", { class: "dictation-words" }, ...result.words.map((w) => el("span", { class: w.ok ? "w-ok" : "w-bad" }, `${w.w} `))));
  if (result.marks) box.append(el("ul", { class: "fr-pair-marks" }, ...result.marks.map((m) => el("li", { class: m.ok ? "w-ok" : "w-bad" }, `${m.left} → ${m.ok ? m.right : m.expected}`))));
  // O áudio só lê francês: a palavra do eixo, a frase corrigida ou a frase do exercício de registro.
  const filled = step.q && step.q.includes("___") && result.answer && !result.answer.includes("…") ? step.q.replace("___", result.answer) : "";
  const say = result.speak !== undefined ? result.speak : step.kind === "w" ? step.audio_after : step.kind === "v" ? "" : step.t === "register" ? step.q : (result.full || filled || result.answer);
  if ((!result.correct || result.score < 1) && result.answer && !result.marks) {
    box.append(el("p", {}, "Resposta: ", el("b", { class: "fr-text" }, result.answer), " ", say ? frAudioButton(say) : null));
  } else if (say && step.t !== "pairs") {
    box.append(el("p", {}, frAudioButton(say, "Ouvir a forma certa"), el("small", { class: "hint" }, " ouvir")));
  }
  if (result.full && result.full !== result.answer) box.append(el("p", { class: "fr-text" }, result.full));
  if (result.explanation) box.append(el("p", {}, result.explanation));
  if (result.translation) box.append(el("p", { class: "hint" }, result.translation));
  if (!result.correct) box.append(el("p", { class: "hint" }, "Sem problema: este item volta daqui a pouco nesta sessão e de novo na revisão. Se você acertar, ganha +5 XP de recuperação."));
  return box;
}

// -- telas de apresentação
function renderRuleStep(step) {
  return el("div", { class: "panel fr-rule-step" },
    el("span", { class: "kind-tag" }, `Unidade ${step.n}`),
    el("h2", {}, step.title),
    el("p", { class: "hint" }, step.goal),
    renderRules(step.rules),
    el("p", { class: "hint" }, "A seguir: exercícios do reconhecimento à produção. Errou? Você recebe uma pista e tenta de novo."),
    frContinueRow("Entendi, vamos praticar"));
}

function renderWordStep(step) {
  const w = step.word;
  const gender = w.g === "m" ? "masculino" : w.g === "f" ? "feminino" : "";
  const go = el("button", { class: "btn primary fr-continue", type: "button", "data-autofocus": true, onclick: async () => {
    go.disabled = true;
    const result = await api("/api/fr/seen", { body: { item_id: step.item_id } }).catch(() => ({ xp: 0 }));
    if (result.xp) { fr.session.xp += result.xp; frFloatXp(go, `+${result.xp} XP`); }
    frNext();
  } }, "Continuar");
  setTimeout(() => frPlay(w.fr, $("#fr-stage .word-card .audio-btn")), 250);
  return el("div", { class: "panel" },
    el("span", { class: "kind-tag" }, `Palavra nova · ${step.theme}`),
    el("div", { class: "word-card" },
      el("div", { class: "headword" }, el("span", { class: "fr-text" }, w.fr), frAudioButton(w.fr)),
      el("div", { class: "meaning" }, w.pt),
      el("div", { class: "meta" }, w.lv ? el("span", { class: "pill" }, w.lv) : null, gender ? el("span", { class: "pill" }, gender) : null,
        w.reg ? el("span", { class: "pill" }, w.reg) : null),
      w.ex ? el("div", { class: "example-row" }, frAudioButton(w.ex), el("div", {}, el("span", { class: "fr-text" }, w.ex), el("small", {}, w.ex_pt))) : null,
      w.n ? el("p", { class: "trap" }, w.n) : null),
    el("div", { class: "next-row" }, go));
}

// -- múltipla escolha (inclui registro, gênero, escuta)
function renderFrChoice(step) {
  const instruction = { register: "Qual é o registro desta frase?", gender: step.instruction, listen: step.instruction, fr_pt: step.instruction, pt_fr: step.instruction }[step.t]
    || (step.q?.includes("___") ? "Escolha a forma correta." : "Escolha a resposta.");
  const panel = el("div", { class: "panel" }, stepHeader(step, instruction));
  const promptRow = el("div", { class: "prompt-audio fr-prompt-audio" });
  if (step.q) promptRow.append(step.t === "pt_fr" ? el("div", { class: "prompt" }, step.q) : sentence(step.q));
  if (step.audio) promptRow.append(frAudioButton(step.audio, "Ouvir de novo"));
  panel.append(promptRow);
  if (step.hint) panel.append(el("div", { class: "hint" }, step.hint));
  const hint = hintBox();
  const options = el("div", { class: "options" });
  let busy = false;
  let finished = false;
  const buttons = step.options.map((option, index) => {
    const button = el("button", { class: `option${step.t === "pt_fr" || step.t === "mc" ? " fr-text" : ""}`, type: "button" },
      el("span", { class: "key" }, index + 1), el("span", {}, option));
    button.addEventListener("click", async () => {
      if (busy || finished || button.disabled) return;
      busy = true;
      try {
        const result = await frSubmit(step, { answer: option });
        if (!result.final) {
          button.classList.add("wrong");
          button.disabled = true;
          showHint(hint, result, step);
          frSfx("bad");
        } else {
          finished = true;
          buttons.forEach((b, i) => {
            b.disabled = true;
            if (step.options[i] === result.answer) b.classList.add("correct");
          });
          if (!result.correct) button.classList.add("wrong");
          hint.hidden = true;
          frFinal(step, result, panel);
          if (step.audio_after) frPlay(step.audio_after);
        }
      } catch (error) {
        toast(error.message);
      } finally {
        busy = false;
      }
    });
    return button;
  });
  options.append(...buttons);
  panel.append(hint, options);
  panel.dataset.keys = "options";
  return panel;
}

// -- respostas digitadas (lacuna, tradução, transformação, ditado)
function accentBar(target) {
  const keys = fr.session?.course?.keys || FR_ACCENTS;
  return el("div", { class: "fr-accents", "aria-label": "Inserir caractere" }, ...keys.map((ch) =>
    el("button", { type: "button", tabindex: "-1", onmousedown: (e) => e.preventDefault(), onclick: () => {
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? target.value.length;
      target.value = target.value.slice(0, start) + ch + target.value.slice(end);
      target.focus();
      target.setSelectionRange(start + ch.length, start + ch.length);
    } }, ch)));
}

function renderFrTyped(step) {
  const instructions = { gap: "Complete a lacuna.", dict: "Ouça e escreva a frase inteira.", transform: step.p, type: step.instruction };
  const panel = el("div", { class: "panel" }, stepHeader(step, instructions[step.t]));
  const long = step.t === "transform" || step.t === "dict";
  const input = long
    ? el("textarea", { rows: 2, class: "fr-input", spellcheck: "false", lang: frLang(), "aria-label": "Sua resposta", "data-autofocus": true })
    : el("input", { type: "text", class: "fr-input", autocomplete: "off", spellcheck: "false", lang: frLang(), "aria-label": "Sua resposta", "data-autofocus": true });
  if (step.start) input.value = step.start;
  if (step.t === "gap") {
    panel.append(sentence(step.q, input));
    if (step.p) panel.append(el("div", { class: "hint" }, step.p));
  } else if (step.t === "dict") {
    panel.append(el("div", { class: "prompt-audio fr-prompt-audio" }, el("div", { class: "prompt" }, "🎧"), frAudioButton(step.audio, "Ouvir de novo")),
      el("p", { class: "hint" }, "Ouça quantas vezes quiser. Acentos e pontuação contam pouco; as terminações contam muito."), input);
  } else if (step.t === "transform") {
    panel.append(el("blockquote", { class: "fr-quote fr-text" }, step.q), input);
  } else {
    panel.append(el("div", { class: "prompt" }, step.q), step.hint ? el("div", { class: "hint" }, `nível ${step.hint}`) : null, input);
  }
  const hint = hintBox();
  const check = el("button", { class: "btn primary", type: "button" }, "Verificar");
  let finished = false;
  const submit = async () => {
    if (finished || check.disabled) return;
    check.disabled = true;
    try {
      const result = await frSubmit(step, { answer: input.value.trim() });
      if (!result.final) {
        showHint(hint, result, step);
        // Mostra onde está o problema sem entregar a palavra certa.
        if (result.words) hint.append(el("p", { class: "dictation-words" }, ...result.words.map((w) => el("span", { class: w.ok ? "w-ok" : "w-bad" }, w.ok ? `${w.w} ` : "••• "))));
        input.classList.remove("shake");
        void input.offsetWidth;
        if (result.verdict !== "empty") { input.classList.add("shake"); frSfx("bad"); }
        input.focus();
        check.disabled = false;
      } else {
        finished = true;
        input.disabled = true;
        input.classList.add(result.correct ? "ok" : "bad");
        hint.hidden = true;
        frFinal(step, result, panel);
        if (step.audio_after) frPlay(step.audio_after);
      }
    } catch (error) {
      toast(error.message);
      check.disabled = false;
    }
  };
  check.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.stopPropagation(); submit(); }
  });
  panel.append(accentBar(input), hint, el("div", { class: "next-row" }, check));
  return panel;
}

// -- caça ao erro
function renderFrFix(step) {
  const panel = el("div", { class: "panel" }, stepHeader(step, "Caça ao erro: toque na parte errada da frase e depois escreva a correção."));
  const hint = hintBox();
  const fixRow = el("div", { class: "fr-fixrow", hidden: true });
  const input = el("input", { type: "text", class: "fr-input", autocomplete: "off", spellcheck: "false", lang: "fr", "aria-label": "Correção do trecho" });
  const check = el("button", { class: "btn primary", type: "button" }, "Verificar");
  let located = false;
  let finished = false;
  const tokens = step.tokens.map((token, index) => {
    const b = el("button", { type: "button", class: "fr-token fr-text" }, token);
    b.addEventListener("click", async () => {
      if (located || finished) return;
      const result = await frSubmit(step, { pick: index }).catch((e) => { toast(e.message); return null; });
      if (!result) return;
      if (result.bad) {
        located = true;
        result.bad.forEach((i) => tokens[i].classList.add("fr-bad"));
        tokens.forEach((t) => { t.disabled = true; });
        fixRow.hidden = false;
        if (result.located) { frSfx("ok"); hint.hidden = true; } else showHint(hint, result, step, false);
        input.focus();
      } else {
        b.classList.add("missed");
        showHint(hint, result, step, false);
        frSfx("bad");
      }
    });
    return b;
  });
  const submit = async () => {
    if (finished || check.disabled) return;
    check.disabled = true;
    try {
      const result = await frSubmit(step, { answer: input.value.trim() });
      if (!result.final) {
        showHint(hint, result, step);
        input.classList.remove("shake"); void input.offsetWidth;
        if (result.verdict !== "empty") { input.classList.add("shake"); frSfx("bad"); }
        check.disabled = false;
        input.focus();
      } else {
        finished = true;
        input.disabled = true;
        hint.hidden = true;
        frFinal(step, result, panel);
        if (result.full) frPlay(result.full);
      }
    } catch (error) {
      toast(error.message);
      check.disabled = false;
    }
  };
  check.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); submit(); } });
  fixRow.append(el("label", { class: "fr-inline-label" }, "Corrija o trecho destacado:"), input, accentBar(input), el("div", { class: "next-row" }, check));
  panel.append(el("div", { class: "fr-tokens" }, ...tokens), hint, fixRow);
  return panel;
}

// -- montagem de frase
function renderFrOrder(step) {
  const panel = el("div", { class: "panel" }, stepHeader(step, "Monte a frase. Atenção: sobra uma palavra."));
  const line = el("div", { class: "order-line", "aria-label": "Sua frase" });
  const pool = el("div", { class: "order-pool" });
  const hint = hintBox();
  const check = el("button", { class: "btn primary", type: "button", disabled: true }, "Verificar");
  let finished = false;
  const refresh = () => { check.disabled = finished || line.children.length < 2; };
  step.tokens.forEach((token) => {
    const chip = el("button", { class: "chip fr-text", type: "button" }, token);
    chip.addEventListener("click", () => {
      if (finished) return;
      (chip.parentElement === pool ? line : pool).append(chip);
      refresh();
    });
    pool.append(chip);
  });
  check.addEventListener("click", async () => {
    if (finished) return;
    check.disabled = true;
    try {
      const result = await frSubmit(step, { answer: [...line.children].map((c) => c.textContent).join(" ") });
      if (!result.final) {
        showHint(hint, result, step);
        line.classList.remove("shake"); void line.offsetWidth; line.classList.add("shake");
        frSfx("bad");
        refresh();
      } else {
        finished = true;
        hint.hidden = true;
        frFinal(step, result, panel);
        frPlay(result.answer);
      }
    } catch (error) {
      toast(error.message);
      refresh();
    }
  });
  panel.append(line, pool, hint, el("div", { class: "next-row" }, check));
  return panel;
}

// -- pares
function renderFrPairs(step) {
  const panel = el("div", { class: "panel" }, stepHeader(step, "Ligue cada item ao seu par: toque num item da esquerda e depois no da direita."));
  const pairs = new Map();
  const colors = ["#2d4fa3", "#c07a3a", "#4a8a4a", "#b06a5a", "#6a5aa0", "#3a8aa0"];
  let selected = null;
  let finished = false;
  const check = el("button", { class: "btn primary", type: "button", disabled: true }, "Verificar");
  const paint = () => {
    leftButtons.forEach((b) => {
      const right = pairs.get(b.dataset.value);
      const index = [...pairs.keys()].indexOf(b.dataset.value);
      b.classList.toggle("selected", selected === b);
      b.classList.toggle("paired", Boolean(right));
      b.style.setProperty("--pair", right ? colors[index % colors.length] : "transparent");
    });
    rightButtons.forEach((b) => {
      const owner = [...pairs.entries()].find(([, r]) => r === b.dataset.value);
      const index = owner ? [...pairs.keys()].indexOf(owner[0]) : -1;
      b.classList.toggle("paired", Boolean(owner));
      b.style.setProperty("--pair", owner ? colors[index % colors.length] : "transparent");
    });
    check.disabled = finished || pairs.size !== step.left.length;
  };
  const leftButtons = step.left.map((value) => {
    const b = el("button", { type: "button", class: "match-item fr-text", dataset: { value } }, value);
    b.addEventListener("click", () => {
      if (finished) return;
      if (pairs.has(value)) pairs.delete(value);
      selected = selected === b ? null : b;
      paint();
    });
    return b;
  });
  const rightButtons = step.right.map((value) => {
    const b = el("button", { type: "button", class: "match-item", dataset: { value } }, value);
    b.addEventListener("click", () => {
      if (finished || !selected) return;
      for (const [k, v] of pairs) if (v === value) pairs.delete(k);
      pairs.set(selected.dataset.value, value);
      selected = null;
      paint();
    });
    return b;
  });
  check.addEventListener("click", async () => {
    check.disabled = true;
    try {
      const result = await frSubmit(step, { answer: [...pairs.entries()].map(([left, right]) => ({ left, right })) });
      finished = true;
      for (const mark of result.marks || []) {
        const b = leftButtons.find((x) => x.dataset.value === mark.left);
        b?.classList.add(mark.ok ? "ok" : "bad");
      }
      frFinal(step, result, panel);
    } catch (error) {
      toast(error.message);
      check.disabled = false;
    }
  });
  panel.append(el("div", { class: "match-grid" }, el("div", { class: "match-col" }, ...leftButtons), el("div", { class: "match-col" }, ...rightButtons)),
    el("div", { class: "next-row" }, check));
  return panel;
}

// ------------------------------------------------------------------ sprint de verbos
function renderSprint() {
  const s = fr.session;
  const stage = $("#fr-stage");
  const clock = el("div", { class: "fr-clock" }, el("span", {}));
  const counter = el("div", { class: "fr-sprint-score" }, el("b", {}, "0"), el("small", {}, "formas certas"));
  const card = el("div", { class: "fr-sprint-q" });
  const input = el("input", { type: "text", class: "fr-input fr-sprint-input", autocomplete: "off", spellcheck: "false", lang: "fr", "aria-label": "Forma do verbo" });
  const flash = el("div", { class: "fr-sprint-flash", role: "status" });
  const panel = el("div", { class: "panel fr-sprint" }, clock, counter, card, input, accentBar(input), flash,
    el("p", { class: "hint" }, "Digite só a forma depois do sujeito (ex.: «allions», «sommes allés», «me lève») e aperte Enter."));
  stage.replaceChildren(panel);
  let left = s.seconds;
  let busy = false;
  let ended = false;
  const total = s.seconds;
  const showQuestion = () => {
    if (s.index >= s.steps.length) { finish(); return; }
    const q = s.steps[s.index];
    card.replaceChildren(el("span", { class: "fr-sprint-subject fr-text" }, q.subject), el("span", { class: "fr-sprint-verb fr-text" }, q.inf),
      el("span", { class: "fr-sprint-tense" }, q.tense_label), el("small", { class: "hint" }, q.pt));
    input.value = "";
    input.disabled = false;
    input.focus();
    frProgress();
  };
  const finish = async () => {
    if (ended) return;
    ended = true;
    clearInterval(s.timer);
    input.disabled = true;
    s.index = s.steps.length;
    stage.replaceChildren(el("p", { class: "loading" }, "Contando os pontos…"));
    stage.replaceChildren(await renderFrSummary());
  };
  input.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter" || busy || ended || !input.value.trim()) return;
    event.preventDefault();
    busy = true;
    const q = s.steps[s.index];
    try {
      const result = await frSubmit(q, { answer: input.value.trim() });
      s.answered += 1;
      s.xp += (result.xp || 0) + (result.bonus || 0);
      if (result.correct) {
        s.sprintScore += 1;
        s.momentum = Math.min(5, s.momentum + 1);
        flash.className = "fr-sprint-flash ok";
        flash.textContent = `✓ ${q.subject} ${result.answer}`;
        frSfx("ok");
      } else {
        s.momentum = Math.max(0, s.momentum - 1);
        s.sprintMiss.push({ q, given: input.value.trim(), answer: result.answer });
        flash.className = "fr-sprint-flash bad";
        flash.textContent = `${q.subject} ${result.answer}`;
        frSfx("bad");
      }
      s.bestMomentum = Math.max(s.bestMomentum, s.momentum);
      if (fr.data) { fr.data.profile.xp_today = result.xp_today ?? fr.data.profile.xp_today; renderFrTopbar(); }
      counter.querySelector("b").textContent = s.sprintScore;
      s.index += 1;
      input.disabled = true;
      setTimeout(() => { busy = false; if (!ended) showQuestion(); }, result.correct ? 250 : 1300);
    } catch (error) {
      toast(error.message);
      busy = false;
    }
  });
  s.timer = setInterval(() => {
    left -= 1;
    clock.firstChild.style.width = `${(left / total) * 100}%`;
    clock.classList.toggle("hurry", left <= 10);
    if (left <= 10 && left > 0) frSfx("tick");
    if (left <= 0) finish();
  }, 1000);
  clock.firstChild.style.width = "100%";
  showQuestion();
}

// ------------------------------------------------------------------ resumo
async function renderFrSummary() {
  const s = fr.session;
  const results = [...s.results.values()];
  const first = results.filter((r) => r.first >= 1).length;
  let finishData = {};
  try {
    const finishUrl = `${s.course.api}/finish`;
    if (s.mode === "challenge") finishData = await api(finishUrl, { body: { mode: "challenge", unit_id: s.unitId } });
    else if (s.mode === "sprint") finishData = await api(finishUrl, { body: { mode: "sprint", score: s.sprintScore } });
    else finishData = await api(finishUrl, { body: { mode: s.mode, unit_id: s.unitId } });
  } catch (_) { /* segue sem o bônus visual */ }
  const courseData = s.course.data();
  if (finishData.profile && courseData) { courseData.profile = finishData.profile; s.course.topbar(); }
  const profile = courseData?.profile;
  const titles = { vocab: "Vocabulário praticado", learn: s.course.id === "kz" ? "Aula concluída" : "Unidade estudada", challenge: "Desafio concluído", review: "Revisão concluída", theme: "Vocabulário estudado",
    notebook: "Erros trabalhados", diagnostic: "Diagnóstico concluído", sprint: "Sprint encerrado" };
  const box = el("div", { class: "panel summary fr-summary" }, el("h2", {}, titles[s.mode] || "Sessão concluída"));
  if (s.mode === "challenge" && finishData.stars !== undefined) {
    box.append(el("div", { class: "fr-big-stars" }, stars(finishData.stars)),
      el("p", { class: "hint" }, finishData.new_best ? "Novo recorde nesta unidade!" : `Seu melhor: ${"★".repeat(finishData.best_stars) || "nenhuma estrela"}. Três estrelas = 95% de acerto de primeira.`));
    if (finishData.stars >= 3) { frConfetti(); frSfx("level"); }
  }
  if (s.mode === "sprint") {
    box.append(el("div", { class: "fr-sprint-result" }, el("b", {}, finishData.score ?? s.sprintScore), el("span", {}, "formas certas em 90 s")),
      el("p", { class: "hint" }, finishData.record ? "Novo recorde! 🎉" : `Recorde: ${finishData.best ?? s.sprintScore}`));
    if (finishData.record) { frConfetti(); frSfx("level"); }
  }
  box.append(el("div", { class: "summary-stats" },
    el("div", {}, el("b", {}, `+${s.xp}`), el("span", {}, "XP nesta sessão")),
    s.mode === "sprint" ? el("div", {}, el("b", {}, s.answered), el("span", {}, "formas tentadas"))
      : el("div", {}, el("b", {}, `${percent(first, results.length)}%`), el("span", {}, "de primeira")),
    el("div", {}, el("b", {}, s.recovered), el("span", {}, "erros recuperados")),
    el("div", {}, el("b", {}, s.bestMomentum), el("span", {}, "fôlego máximo"))));
  if (profile) {
    box.append(el("div", { class: "fr-goal summary-goal" }, goalRing(profile.xp_today, profile.goal, 78),
      el("div", {}, el("strong", {}, profile.xp_today >= profile.goal ? "Meta do dia cumprida!" : `Faltam ${profile.goal - profile.xp_today} XP para a meta`),
        el("small", { class: "hint" }, `Nível ${profile.level} · ${profile.title}`))));
  }
  if (s.mode === "diagnostic") {
    const byUnit = results.filter((r) => r.first < 1).map((r) => r.step.unit_title);
    box.append(el("h3", {}, byUnit.length ? "Comece por estas unidades" : "Excelente base!"),
      byUnit.length ? el("ul", {}, ...[...new Set(byUnit)].map((t) => el("li", {}, t))) : el("p", {}, "Você acertou tudo de primeira: siga pela fase 2 e use o desafio de cada unidade para conferir."),
      el("p", { class: "hint" }, "As unidades que você acertou de primeira podem ser feitas direto pelo desafio."));
  }
  const missed = s.mode === "sprint" ? s.sprintMiss.map((m) => ({ label: `${m.q.subject} · ${m.q.inf} · ${m.q.tense_label} → ${m.answer}` }))
    : results.filter((r) => r.first < 1).map((r) => ({ label: r.label }));
  if (missed.length && s.mode !== "diagnostic") {
    box.append(el("h3", {}, "Para fixar"), el("p", { class: "hint" }, "Estes itens voltam em cerca de dez minutos e depois em intervalos cada vez maiores."),
      el("div", { class: "summary-list" }, ...missed.slice(0, 14).map((m) => el("div", { class: "fr-text" }, m.label))));
  }
  const again = () => frStart(s.url, s.course);
  s.course.summaryExtra?.(box, finishData, s);
  box.append(el("div", { class: "next-row" },
    el("button", { class: "btn", type: "button", onclick: frEndSession }, "Voltar ao curso"),
    el("button", { class: "btn primary fr-continue", type: "button", "data-autofocus": true, onclick: again },
      { sprint: "Outro sprint", challenge: "Tentar de novo", vocab: "De novo", learn: s.course.id === "kz" ? "Refazer a aula" : "Continuar praticando", review: "Revisar mais", theme: "Mais palavras", notebook: "Continuar", diagnostic: "Refazer" }[s.mode] || "De novo")));
  return box;
}

// ------------------------------------------------------------------ teclado
document.addEventListener("keydown", (event) => {
  if (!fr.session || $("#view-fr-session").hidden || !$("#modal").hidden) return;
  const tag = event.target.tagName;
  if (event.key === "Enter" && tag !== "INPUT" && tag !== "TEXTAREA") {
    const cont = $("#fr-stage .fr-continue");
    if (cont) { event.preventDefault(); cont.click(); }
    return;
  }
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  const panel = $("#fr-stage .panel");
  if (panel?.dataset.keys === "options" && /^[1-4]$/.test(event.key)) {
    const option = panel.querySelectorAll(".option")[Number(event.key) - 1];
    if (option && !option.disabled) option.click();
  }
});

// ------------------------------------------------------------------ início
// O curso de cazaque (kazakh.js) carrega depois deste arquivo e abre a própria página.
if (currentCourse() !== "kz") setCourse(currentCourse());
