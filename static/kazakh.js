"use strict";

/* LinguaLab · Қазақша — curso de cazaque em 40 aulas sequenciais (A1 → B1).
   A trilha é um mapa: cada aula abre a seguinte. Cada aula tem explicação narrada, sons (módulo 0),
   vocabulário com áudio, diálogo em duas vozes (Aigul e Daulet), leitura (aulas finais) e exercícios.
   Os exercícios usam o mesmo executor de sessão do francês (french.js), com a API /api/kz. */

const kz = { data: null, tab: "trilha", loading: null };
const KZ_TABS = [["trilha", "Trilha das aulas"], ["alfabeto", "Alfabeto"], ["conquistas", "Conquistas"]];
const KZ_KEYS = ["ә", "ғ", "қ", "ң", "ө", "ұ", "ү", "һ", "і", "—", "«", "»"];
const KZ_SPECIAL = new Set(["Ә", "Ғ", "Қ", "Ң", "Ө", "Ұ", "Ү", "Һ", "І"]);
// As 42 letras, cada uma com uma palavra para ouvir.
const KZ_ALPHABET = [
  ["А", "ата", "avô"], ["Ә", "әке", "pai"], ["Б", "бала", "criança"], ["В", "вагон", "vagão"], ["Г", "гүл", "flor"], ["Ғ", "ғалым", "cientista"],
  ["Д", "дала", "estepe"], ["Е", "ел", "país"], ["Ё", "ёлка", "pinheiro (palavra russa)"], ["Ж", "жол", "caminho"], ["З", "заң", "lei"], ["И", "ит", "cão"],
  ["Й", "ай", "lua"], ["К", "көл", "lago"], ["Қ", "қала", "cidade"], ["Л", "лимон", "limão"], ["М", "мектеп", "escola"], ["Н", "нан", "pão"],
  ["Ң", "таң", "amanhecer"], ["О", "он", "dez"], ["Ө", "өмір", "vida"], ["П", "пышақ", "faca"], ["Р", "рақмет", "obrigado"], ["С", "су", "água"],
  ["Т", "тау", "montanha"], ["У", "уақыт", "tempo"], ["Ұ", "ұл", "filho"], ["Ү", "үй", "casa"], ["Ф", "фильм", "filme"], ["Х", "хат", "carta"],
  ["Һ", "гауһар", "diamante"], ["Ц", "цирк", "circo"], ["Ч", "чек", "recibo"], ["Ш", "шай", "chá"], ["Щ", "щётка", "escova"], ["Ъ", "подъезд", "entrada do prédio"],
  ["Ы", "ыдыс", "louça"], ["І", "іс", "assunto"], ["Ь", "пальто", "casaco"], ["Э", "экран", "tela"], ["Ю", "юрист", "advogado"], ["Я", "яғни", "ou seja"],
];

const KZ_COURSE = {
  id: "kz", api: "/api/kz", lang: "kk", keys: KZ_KEYS, home: "#view-kz",
  data: () => kz.data, topbar: () => renderKzTopbar(), reload: () => kzLoad(true),
  renderers: { lesson: renderKzLessonStep, vocab: renderKzVocabStep, dialog: renderKzDialogStep, reading: renderKzReadingStep },
  summaryExtra: kzSummaryExtra,
};

// ------------------------------------------------------------------ dados
async function kzLoad(force = false) {
  if (kz.loading) return kz.loading;
  if (kz.data && !force) { renderKzHome(); return null; }
  kz.loading = (async () => {
    try {
      kz.data = await api("/api/kz/overview");
      renderKzHome();
    } catch (error) {
      $("#kz-panel").replaceChildren(el("p", { class: "loading" }, `Não foi possível carregar o curso de cazaque: ${error.message}`));
    } finally {
      kz.loading = null;
    }
  })();
  return kz.loading;
}

function kzLessons() {
  return kz.data ? kz.data.modules.flatMap((m) => m.lessons) : [];
}

function kzStart(lessonId, mode = "learn") {
  frStart(`/api/kz/session?id=${encodeURIComponent(lessonId)}&mode=${mode}`, KZ_COURSE);
}

/** Toca uma lista de falas em sequência (diálogo, vocabulário). */
function kzPlaySequence(entries, onLine = () => {}) {
  let index = 0;
  const playNext = () => {
    if (index >= entries.length) { onLine(-1); return; }
    const [text, voice, button] = entries[index];
    onLine(index);
    const audio = frPlay(text, button, voice);
    index += 1;
    if (!audio) { playNext(); return; }
    audio.addEventListener("ended", () => setTimeout(playNext, 450), { once: true });
  };
  playNext();
}

// ------------------------------------------------------------------ página inicial
function renderKzTopbar() {
  if (!kz.data) return;
  const p = kz.data.profile;
  const parts = [
    el("span", {}, el("b", {}, `Nv. ${p.level}`), ` ${p.title}`),
    el("span", { class: p.xp_today >= p.goal ? "goal-done" : "" }, el("b", {}, number.format(p.xp_today)), `/${p.goal} XP hoje`),
  ];
  if (p.streak) parts.push(el("span", {}, "🔥 ", el("b", {}, p.streak), p.streak === 1 ? " dia" : " dias"));
  parts.push(el("span", {}, el("b", {}, `${kz.data.done}/${kz.data.total}`), " aulas"));
  $("#kz-topbar-stats").replaceChildren(...parts);
}

function renderKzHome() {
  if (!kz.data) return;
  renderKzTopbar();
  const p = kz.data.profile;
  const next = kzLessons().find((l) => l.id === kz.data.next);
  const sfxOn = frStore("fr-sfx") !== "off";
  const actions = el("div", { class: "fr-actions" });
  if (next) {
    actions.append(el("button", { class: `btn${p.due ? "" : " primary"}`, type: "button", onclick: () => kzStart(next.id) },
      next.seen ? "Continuar a aula" : (next.n === 1 ? "Começar o curso" : "Próxima aula"), el("small", {}, `Aula ${next.n} · ${next.title}`)));
  } else if (kz.data.done === kz.data.total) {
    actions.append(el("div", { class: "kz-finished" }, "🏆 Curso concluído! Use o desafio de cada aula para ganhar estrelas."));
  }
  actions.append(el("button", { class: `btn${p.due ? " primary" : ""}`, type: "button", disabled: p.seen === 0, onclick: () => frStart("/api/kz/session?kind=review", KZ_COURSE) },
    p.due ? "Revisar agora" : "Revisão", el("small", {}, p.due ? `${number.format(p.due)} itens esperando` : p.seen ? "nada vence hoje" : "nada estudado ainda")));

  $("#kz-hero").replaceChildren(
    el("div", { class: "fr-hero-text" },
      el("h1", {}, "Қазақ тілі ", el("span", { class: "fr-level-tag" }, "A1 → B1")),
      el("p", {}, "Do som das letras ao B1 em 40 aulas. Cada aula abre a seguinte; errar só abre uma pista e uma nova tentativa, e o XP nunca diminui."),
      el("div", { class: "fr-level" },
        el("div", { class: "fr-level-badge kz-badge" }, el("b", {}, p.level), el("small", {}, "деңгей")),
        el("div", { class: "fr-level-info" },
          el("strong", {}, p.title, el("span", { class: "hint" }, ` · ${p.title_pt}`)),
          el("div", { class: "fr-xpbar" }, el("span", { style: { width: `${percent(p.into, p.span)}%` } })),
          el("small", {}, `${number.format(p.into)} / ${number.format(p.span)} XP até o próximo nível · ${number.format(p.xp_total)} XP no total`))),
      actions),
    el("div", { class: "fr-hero-side" },
      el("div", { class: "fr-goal" }, goalRing(p.xp_today, p.goal),
        el("div", {}, el("strong", {}, p.xp_today >= p.goal ? "Meta cumprida!" : "Meta do dia"),
          el("button", { class: "text-button", type: "button", onclick: kzSettingsModal }, "meta e modo livre"))),
      el("div", { class: "fr-mini-stats" },
        el("div", {}, el("b", {}, `🔥 ${p.streak}`), el("small", {}, p.streak === 1 ? "dia seguido" : "dias seguidos")),
        el("div", {}, el("b", {}, `${kz.data.done}/${kz.data.total}`), el("small", {}, "aulas")),
        el("div", {}, el("b", {}, number.format(p.mastered)), el("small", {}, "dominados"))),
      el("button", { class: "text-button", type: "button", onclick: () => { frStore("fr-sfx", sfxOn ? "off" : "on"); renderKzHome(); } },
        sfxOn ? "🔊 sons ligados" : "🔇 sons desligados")));

  $("#kz-tabs").replaceChildren(...KZ_TABS.map(([id, label]) =>
    el("button", { type: "button", "aria-pressed": String(kz.tab === id), onclick: () => { kz.tab = id; renderKzHome(); } }, label)));
  const panel = $("#kz-panel");
  if (kz.tab === "alfabeto") panel.replaceChildren(renderKzAlphabet());
  else if (kz.tab === "conquistas") panel.replaceChildren(renderKzAchievements());
  else panel.replaceChildren(renderKzTrail());
}

function kzSettingsModal() {
  const select = el("select", {}, ...FR_GOALS.map(([value, label]) => el("option", { value, selected: value === kz.data.profile.goal }, label)));
  const free = el("input", { type: "checkbox", checked: kz.data.free_mode });
  openModal(el("div", {},
    el("h2", { id: "modal-title" }, "Preferências do cazaque"),
    el("div", { class: "settings-grid" },
      el("label", {}, "Meta diária (XP)", select),
      el("label", { class: "kz-check" }, free, " Modo livre: abrir todas as aulas, sem esperar a anterior")),
    el("p", { class: "hint" }, "O curso foi pensado em sequência: cada aula usa o que as anteriores ensinaram. O modo livre serve para quem já sabe parte do conteúdo."),
    el("div", { class: "next-row" }, el("button", { class: "btn primary", type: "button", onclick: async () => {
      await api("/api/kz/goal", { body: { goal: Number(select.value) } });
      await api("/api/kz/free", { body: { on: free.checked } });
      closeModal();
      kzLoad(true);
    } }, "Salvar"))));
}

// -- trilha: um caminho em zigue-zague, módulo por módulo
function renderKzTrail() {
  const wrap = el("div", { class: "kz-trail" });
  let index = 0;
  for (const module of kz.data.modules) {
    const done = module.lessons.filter((l) => l.done).length;
    const section = el("section", { class: "kz-module" },
      el("header", {}, el("h2", {}, module.title), el("span", { class: "fr-level-tag" }, module.level),
        el("small", { class: "hint" }, `${done}/${module.lessons.length} aulas`)));
    const path = el("div", { class: "kz-path" });
    for (const lesson of module.lessons) {
      path.append(kzNode(lesson, index));
      index += 1;
    }
    section.append(path);
    wrap.append(section);
  }
  return wrap;
}

function kzNode(lesson, index) {
  const state = !lesson.unlocked ? "locked" : lesson.done ? "done" : lesson.id === kz.data.next ? "current" : "open";
  const side = ["left", "mid", "right", "mid"][index % 4];
  return el("button", { class: `kz-node ${state} ${side}`, type: "button", onclick: () => openKzLesson(lesson),
    title: state === "locked" ? "Conclua a aula anterior para abrir" : lesson.title },
    el("span", { class: "kz-node-dot" }, state === "locked" ? "🔒" : state === "done" ? "✓" : lesson.n),
    el("span", { class: "kz-node-text" },
      el("small", {}, `Aula ${lesson.n} · ${lesson.level}`),
      el("strong", {}, lesson.title),
      el("span", { class: "kz-node-kz fr-text" }, lesson.kz),
      el("span", { class: "kz-node-foot" }, stars(lesson.stars),
        lesson.due ? el("span", { class: "due" }, `${lesson.due} para revisar`) : el("span", {}, state === "current" ? "▶ sua próxima aula" : lesson.seen && !lesson.done ? `${lesson.seen}/${lesson.total}` : ""))));
}

async function openKzLesson(lesson) {
  if (!lesson.unlocked) {
    const prev = kzLessons().find((l) => l.n === lesson.n - 1);
    toast(`Aula trancada. Conclua a aula ${prev ? `${prev.n} (${prev.title})` : "anterior"} para abrir esta, ou ligue o modo livre.`);
    return;
  }
  let detail;
  try {
    detail = await api(`/api/kz/lesson?id=${encodeURIComponent(lesson.id)}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  const learn = el("button", { class: "btn primary", type: "button", onclick: () => { closeModal(); kzStart(lesson.id); } },
    lesson.done ? "Refazer a aula" : lesson.seen ? "Continuar a aula" : "Começar a aula",
    el("small", {}, `explicação, vocabulário, diálogo e ${lesson.total} exercícios`));
  const challenge = el("button", { class: "btn", type: "button", disabled: !lesson.done, onclick: () => { closeModal(); kzStart(lesson.id, "challenge"); } },
    "Desafio ★", el("small", {}, lesson.done ? `sem explicação · melhor: ${"★".repeat(lesson.stars) || "nenhuma estrela"}` : "abre quando você concluir a aula"));
  const vocab = el("button", { class: "btn", type: "button", onclick: () => { closeModal(); kzStart(lesson.id, "vocab"); } },
    "Vocabulário", el("small", {}, `${detail.words.length} palavras e expressões`));
  const narrate = el("button", { class: "btn small", type: "button" }, "🔊 Ouvir a explicação");
  narrate.addEventListener("click", () => frPlay("", narrate, "", `/api/kz/narration?id=${encodeURIComponent(lesson.id)}`));
  openModal(el("div", { class: "fr-unit-modal kz-modal" },
    el("span", { class: "kind-tag" }, `Aula ${detail.n} · ${detail.level} · ${detail.module}`),
    el("h2", { id: "modal-title" }, detail.title),
    el("p", { class: "fr-text kz-subtitle" }, detail.kz),
    el("p", { class: "hint" }, detail.goal),
    el("div", { class: "fr-modal-actions" }, learn, challenge, vocab),
    el("h3", {}, "A aula ", narrate),
    renderRules(detail.rules),
    detail.sounds?.length ? renderKzSounds(detail.sounds) : null,
    el("h3", {}, "Vocabulário"),
    el("div", { class: "kz-words" }, ...detail.words.map((w) => el("div", { class: "kz-word" }, frAudioButton(w.kz),
      el("span", { class: "fr-text" }, w.kz), el("small", {}, w.pt), stageDot(w.stage))))));
}

// -- alfabeto
function renderKzAlphabet() {
  return el("div", {},
    el("p", { class: "hint fr-panel-intro" }, "As 42 letras do alfabeto cazaque em cirílico. As 9 em destaque não existem em russo: são os sons que o módulo 0 treina. Toque numa letra para ouvir a palavra de exemplo."),
    el("div", { class: "kz-alphabet" }, ...KZ_ALPHABET.map(([letter, word, pt]) => {
      const card = el("button", { class: `kz-letter${KZ_SPECIAL.has(letter) ? " special" : ""}`, type: "button" },
        el("b", { class: "fr-text" }, `${letter} ${letter.toLowerCase()}`), el("span", { class: "fr-text" }, word), el("small", {}, pt));
      card.addEventListener("click", () => frPlay(word, card));
      return card;
    })));
}

function renderKzAchievements() {
  const list = kz.data.achievements;
  const done = list.filter((a) => a.done).length;
  return el("div", {},
    el("p", { class: "hint fr-panel-intro" }, `${done} de ${list.length} conquistas.`),
    el("div", { class: "fr-badges" }, ...list.map((a) => el("div", { class: `fr-badge${a.done ? " done" : ""}` },
      el("span", { class: "fr-badge-icon" }, a.done ? "🏅" : "🔒"), el("strong", { class: "fr-text" }, a.title), el("small", {}, a.desc)))));
}

// ------------------------------------------------------------------ telas da aula
function renderKzSounds(sounds) {
  return el("div", { class: "kz-sounds" }, ...sounds.map((s) => el("section", { class: "kz-sound" },
    el("div", { class: "kz-sound-letter fr-text" }, s.l),
    el("p", {}, s.pt),
    el("div", { class: "kz-sound-words" }, ...s.words.map(([w, pt]) => el("span", { class: "kz-sound-word" }, frAudioButton(w), el("b", { class: "fr-text" }, w), el("small", {}, pt)))))));
}

function renderKzLessonStep(step) {
  const narrate = el("button", { class: "btn", type: "button" }, "🔊 Ouvir a explicação");
  narrate.addEventListener("click", () => frPlay("", narrate, "", `/api/kz/narration?id=${encodeURIComponent(step.lesson_id)}`));
  return el("div", { class: "panel fr-rule-step kz-lesson-step" },
    el("span", { class: "kind-tag" }, `Aula ${step.n} · ${step.level}`),
    el("h2", {}, step.title),
    el("p", { class: "fr-text kz-subtitle" }, step.kz),
    el("p", { class: "hint" }, `Objetivo: ${step.goal}`),
    el("div", { class: "kz-narrate" }, narrate, el("small", { class: "hint" }, "narração em português, com os exemplos em cazaque")),
    step.sounds?.length ? el("h3", {}, "Os sons") : null,
    step.sounds?.length ? renderKzSounds(step.sounds) : null,
    renderRules(step.rules),
    el("p", { class: "hint" }, "A seguir: as palavras da aula, o diálogo e os exercícios. Errou? Você recebe uma pista e tenta de novo."),
    frContinueRow("Vamos às palavras"));
}

function renderKzVocabStep(step) {
  const buttons = [];
  const rows = step.words.map((w) => {
    const button = frAudioButton(w.kz);
    buttons.push([w.kz, "", button]);
    return el("div", { class: "kz-word" }, button, el("span", { class: "fr-text" }, w.kz), el("small", {}, w.pt), w.note ? el("em", { class: "hint" }, w.note) : null);
  });
  const listen = el("button", { class: "btn", type: "button" }, "🔊 Ouvir todas");
  listen.addEventListener("click", () => kzPlaySequence(buttons, (i) => rows.forEach((r, j) => r.classList.toggle("speaking", i === j))));
  const go = el("button", { class: "btn primary fr-continue", type: "button", "data-autofocus": true, onclick: async () => {
    go.disabled = true;
    const result = await api("/api/kz/seen", { body: { item_ids: step.words.map((w) => w.id) } }).catch(() => ({ xp: 0 }));
    if (result.xp) { fr.session.xp += result.xp; frFloatXp(go, `+${result.xp} XP`); }
    frNext();
  } }, "Já ouvi, vamos treinar");
  return el("div", { class: "panel" },
    el("span", { class: "kind-tag" }, `Aula ${step.n} · vocabulário`),
    el("h2", {}, "Palavras e expressões"),
    el("p", { class: "hint" }, "Ouça cada uma e repita em voz alta. Logo depois vem um treino rápido de reconhecimento."),
    el("div", { class: "next-row kz-left" }, listen),
    el("div", { class: "kz-words" }, ...rows),
    el("div", { class: "next-row" }, go));
}

function renderKzDialogStep(step) {
  const showPt = frStore("kz-dialog-pt") !== "off";
  const entries = [];
  const rows = step.lines.map((line) => {
    const button = frAudioButton(line.kz, "Ouvir a fala", line.voice);
    entries.push([line.kz, line.voice, button]);
    return el("div", { class: `kz-line ${line.who === "A" ? "a" : "b"}` },
      el("span", { class: "kz-avatar", title: line.voice === "m" ? "Daulet" : "Aigul" }, line.voice === "m" ? "Д" : "А"),
      el("div", { class: "kz-bubble" }, el("div", {}, button, el("span", { class: "fr-text" }, line.kz)), el("small", { class: "kz-pt", hidden: !showPt }, line.pt)));
  });
  const play = el("button", { class: "btn", type: "button" }, "▶ Ouvir o diálogo");
  play.addEventListener("click", () => kzPlaySequence(entries, (i) => rows.forEach((r, j) => r.classList.toggle("speaking", i === j))));
  const toggle = el("button", { class: "text-button", type: "button" }, showPt ? "esconder tradução" : "mostrar tradução");
  toggle.addEventListener("click", () => {
    const hide = !rows[0].querySelector(".kz-pt").hidden;
    rows.forEach((r) => { r.querySelector(".kz-pt").hidden = hide; });
    toggle.textContent = hide ? "mostrar tradução" : "esconder tradução";
    frStore("kz-dialog-pt", hide ? "off" : "on");
  });
  return el("div", { class: "panel" },
    el("span", { class: "kind-tag" }, "Diálogo"),
    el("h2", {}, step.title),
    el("p", { class: "hint" }, "Ouça o diálogo inteiro, depois fala por fala. Tente ler junto (sombreamento) antes de olhar a tradução."),
    el("div", { class: "next-row kz-left" }, play, toggle),
    el("div", { class: "kz-dialog" }, ...rows),
    frContinueRow("Agora os exercícios"));
}

function renderKzReadingStep(step) {
  const entries = [];
  const paragraphs = step.paragraphs.map((p) => {
    const button = frAudioButton(p.kz, "Ouvir o parágrafo");
    entries.push([p.kz, "", button]);
    const pt = el("p", { class: "kz-pt hint", hidden: true }, p.pt);
    const show = el("button", { class: "text-button", type: "button", onclick: () => { pt.hidden = !pt.hidden; show.textContent = pt.hidden ? "tradução" : "esconder"; } }, "tradução");
    return el("div", { class: "kz-paragraph" }, el("div", { class: "kz-paragraph-head" }, button, show), el("p", { class: "fr-text" }, p.kz), pt);
  });
  const play = el("button", { class: "btn", type: "button" }, "▶ Ouvir o texto todo");
  play.addEventListener("click", () => kzPlaySequence(entries, (i) => paragraphs.forEach((r, j) => r.classList.toggle("speaking", i === j))));
  return el("div", { class: "panel" },
    el("span", { class: "kind-tag" }, "Leitura"),
    el("h2", { class: "fr-text" }, step.title),
    el("p", { class: "hint" }, "Leia primeiro sem tradução, procurando nomes e números. Depois ouça e confira só o que não entendeu."),
    el("div", { class: "next-row kz-left" }, play),
    ...paragraphs,
    frContinueRow("Responder às perguntas"));
}

// -- fim da sessão: próxima aula aberta
function kzSummaryExtra(box, finishData, session) {
  const next = finishData.next;
  if (session.mode !== "learn" || !finishData.lesson_done) {
    if (session.mode === "learn" && finishData.lesson_done === false) {
      box.append(el("p", { class: "hint" }, "Ainda faltam exercícios desta aula. Refaça a aula para abrir a próxima."));
    }
    return;
  }
  if (next?.unlocked) {
    frConfetti();
    frSfx("level");
    box.append(el("div", { class: "fr-callout kz-unlock" }, el("strong", {}, `🔓 Aula ${next.n} desbloqueada: ${next.title}`),
      el("button", { class: "btn primary small", type: "button", onclick: () => kzStart(next.id) }, "Começar agora")));
  } else if (!next) {
    frConfetti();
    box.append(el("div", { class: "fr-callout" }, el("strong", {}, "🏆 Você concluiu as 40 aulas! Құттықтаймын!")));
  }
}

// ------------------------------------------------------------------ início
if (currentCourse() === "kz") setCourse("kz");
