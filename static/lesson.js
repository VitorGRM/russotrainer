"use strict";

/* LinguaLab Russo · aulas temáticas.
   Telas de aula (vocabulário, escuta, leitura, foco na forma, lacunas, pares, repetição, produção),
   player de diálogos com várias vozes e o bloco da aula na gaveta do tema. */

// ------------------------------------------------------------------ player de várias falas
const activePlayers = new Set();

function stopAllAudio() {
  activePlayers.forEach((player) => player.stop());
  if (currentAudio) currentAudio.pause();
}

/** Toca uma sequência de falas, cada uma com a sua voz. Devolve o elemento do player. */
function linePlayer(lines, { label = "Ouvir", autoplay = false, compact = false, unit = "falas" } = {}) {
  let index = 0;
  let playing = false;
  let audio = null;
  let rate = 1;
  const status = el("span", { class: "player-status" }, lines.length > 1 ? `${lines.length} ${unit}` : "");
  const playButton = el("button", { class: "btn player-play", type: "button" }, svgIcon("M8 5v14l11-7z"), el("span", {}, label));
  const restart = el("button", { class: "text-button", type: "button", title: "Do começo" }, "↺ do começo");
  const speed = el("button", { class: "text-button", type: "button", title: "Velocidade" }, "velocidade normal");
  const urlFor = (line) => `/api/tts?text=${encodeURIComponent(line.text)}${line.voice ? `&voice=${line.voice}` : ""}`;

  const player = {
    stop() {
      playing = false;
      if (audio) audio.pause();
      playButton.querySelector("span").textContent = index > 0 && index < lines.length ? "Continuar" : label;
      wrap.classList.remove("is-playing");
    },
  };
  const playFrom = (start) => {
    stopAllAudio();
    activePlayers.add(player);
    index = start;
    playing = true;
    wrap.classList.add("is-playing");
    playButton.querySelector("span").textContent = "Pausar";
    const step = () => {
      if (!playing) return;
      if (index >= lines.length) {
        index = 0;
        player.stop();
        status.textContent = lines.length > 1 ? `${lines.length} ${unit} · fim` : "";
        return;
      }
      status.textContent = lines.length > 1 ? `${index + 1} de ${lines.length}` : "tocando";
      audio = new Audio(urlFor(lines[index]));
      audio.playbackRate = rate;
      if (index + 1 < lines.length) new Audio(urlFor(lines[index + 1])).preload = "auto";
      audio.addEventListener("ended", () => { index += 1; setTimeout(step, 380); });
      audio.addEventListener("error", () => {
        player.stop();
        toast("Áudio indisponível agora. Verifique a conexão com a internet.");
      });
      audio.play().catch(() => player.stop());
    };
    step();
  };
  playButton.addEventListener("click", () => (playing ? player.stop() : playFrom(index)));
  restart.addEventListener("click", () => playFrom(0));
  speed.addEventListener("click", () => {
    rate = rate === 1 ? 0.8 : 1;
    speed.textContent = rate === 1 ? "velocidade normal" : "mais devagar";
    if (audio) audio.playbackRate = rate;
  });
  const wrap = el("div", { class: `line-player${compact ? " compact" : ""}` }, playButton, status, lines.length > 1 ? restart : null, speed);
  if (autoplay) setTimeout(() => playFrom(0), 300);
  return wrap;
}

// ------------------------------------------------------------------ gravação da própria voz
function recorder() {
  const box = el("div", { class: "recorder" });
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    box.append(el("small", { class: "hint" }, "Gravação indisponível aqui: fale em voz alta."));
    return box;
  }
  let media = null;
  let chunks = [];
  const record = el("button", { class: "btn small", type: "button" }, "● Gravar");
  const playback = el("audio", { controls: true, hidden: true });
  record.addEventListener("click", async () => {
    if (media && media.state === "recording") {
      media.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      media = new MediaRecorder(stream);
      media.addEventListener("dataavailable", (e) => chunks.push(e.data));
      media.addEventListener("stop", () => {
        stream.getTracks().forEach((t) => t.stop());
        playback.src = URL.createObjectURL(new Blob(chunks, { type: media.mimeType }));
        playback.hidden = false;
        record.textContent = "● Gravar de novo";
        record.classList.remove("recording");
      });
      stopAllAudio();
      media.start();
      record.textContent = "■ Parar";
      record.classList.add("recording");
    } catch (_) {
      box.replaceChildren(el("small", { class: "hint" }, "Sem acesso ao microfone: fale em voz alta."));
    }
  });
  box.append(record, playback);
  return box;
}

// ------------------------------------------------------------------ sessão de aula
async function startLesson(lessonId, part = 0) {
  let data;
  try {
    data = await api(`/api/aula?id=${encodeURIComponent(lessonId)}&part=${part}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  const theme = themeById(data.theme.id) || data.theme;
  stopAllAudio();
  state.session = { theme, mode: "lesson", lessonId, part, steps: data.steps, index: 0, results: new Map(), retried: new Set(), introduced: 0, answered: 0 };
  $("#view-gallery").hidden = true;
  $("#view-session").hidden = false;
  $("#view-session").style.setProperty("--tab", theme.color);
  $("#session-title").replaceChildren(`Aula · ${theme.name} · Parte ${part + 1}: ${data.part_title}`);
  window.scrollTo(0, 0);
  renderStep();
}

function lessonPanel(phase, ...children) {
  return el("div", { class: "panel lesson-panel" }, phase ? el("span", { class: "kind-tag" }, phase) : null, ...children);
}

function nextButton(label = "Continuar") {
  const button = el("button", { class: "btn primary", type: "button", "data-autofocus": true, onclick: next }, label);
  return el("div", { class: "next-row" }, button);
}

function renderPartIntro(step) {
  const objectives = step.objectives?.length
    ? el("div", { class: "objectives" }, el("h3", {}, "Ao final da aula, você vai conseguir:"),
      el("ul", {}, ...step.objectives.map((o) => el("li", {}, o))))
    : null;
  return lessonPanel(`Parte ${step.part_number} de ${step.parts}`,
    el("h2", { class: "lesson-title ru" }, step.lesson_title),
    el("p", { class: "lesson-subtitle" }, step.lesson_title_pt, step.level ? ` · ${step.level}` : ""),
    el("h3", { class: "part-title" }, step.part_title),
    step.goal ? el("p", {}, step.goal) : null,
    objectives,
    step.grammar_focus ? el("p", { class: "hint" }, "Foco gramatical: ", ruText(step.grammar_focus, "")) : null,
    nextButton("Começar"));
}

function renderWarmup(step) {
  return lessonPanel(step.phase,
    el("p", { class: "instruction" }, "Antes de começar, pense nestas perguntas e, se puder, responda em voz alta. Não há resposta certa."),
    el("ul", { class: "warmup" }, ...step.questions.map((q) =>
      el("li", {}, /[а-яё]/i.test(q) ? el("span", {}, ruText(q, ""), " ", audioButton(q)) : q))),
    step.note ? el("p", { class: "hint" }, step.note) : null,
    nextButton());
}

function renderVocab(step) {
  const cards = step.items.map((item) => el("div", { class: "vocab-card" },
    el("div", { class: "vocab-ru" }, ruText(item.ru), audioButton(item.ru)),
    el("div", { class: "vocab-pt" }, item.pt),
    item.note ? el("div", { class: "vocab-note" }, ruText(item.note, "")) : null,
    item.example ? el("div", { class: "vocab-example" }, ruText(item.example), " ", audioButton(item.example), item.example_pt ? el("small", {}, item.example_pt) : null) : null));
  return lessonPanel(step.phase,
    el("p", { class: "instruction" }, "Ouça cada expressão, leia a nota e repita em voz alta. Em seguida você vai recuperá-las sem olhar."),
    el("div", { class: "vocab-grid" }, ...cards),
    nextButton("Já li: testar"));
}

function renderGrammar(step) {
  const panel = lessonPanel(step.phase, el("h2", { class: "grammar-title" }, step.title || ""));
  (step.paragraphs || []).forEach((p) => panel.append(el("p", { class: "grammar-p" }, ruText(p, ""))));
  if (step.table?.rows?.length) {
    panel.append(el("div", { class: "table-wrap" }, el("table", { class: "memory-table" },
      el("tr", {}, ...(step.table.columns || []).map((c) => el("th", {}, c))),
      ...step.table.rows.map((r) => el("tr", {}, ...r.map((c) => el("td", {}, ruText(c, ""))))))));
  }
  if (step.examples?.length) {
    panel.append(el("div", { class: "examples" }, ...step.examples.map((ex) =>
      el("div", { class: "example-row" }, audioButton(ex[0]), el("div", {}, ruText(ex[0]), el("small", {}, ex[1] || ""))))));
  }
  if (step.pitfalls?.length) {
    panel.append(el("h3", { class: "pitfalls-title" }, "Cuidado com estes erros"),
      el("ul", { class: "pitfalls" }, ...step.pitfalls.map((p) => el("li", {}, ruText(p, "")))));
  }
  panel.append(nextButton("Entendi: praticar"));
  return panel;
}

function renderListen(step) {
  const dialogue = step.audio_lines.length > 1;
  return lessonPanel(step.phase,
    el("h2", { class: "listen-title ru" }, step.title),
    step.setting ? el("p", { class: "setting" }, step.setting) : null,
    step.speakers?.length ? el("p", { class: "hint" }, "Vozes: ", step.speakers.join(", ")) : null,
    el("div", { class: "listen-box" },
      linePlayer(step.audio_lines, { label: dialogue ? "Ouvir o diálogo" : "Ouvir", autoplay: true })),
    el("p", { class: "instruction" }, dialogue
      ? "Primeira escuta, sem texto: descubra quem fala, onde estão e sobre o quê. Nas perguntas seguintes você pode ouvir de novo quantas vezes quiser."
      : "Primeira escuta: identifique o tipo de texto e a informação principal. Nas perguntas, você pode ouvir de novo."),
    nextButton("Ir às perguntas"));
}

function renderTranscript(step) {
  let showPt = false;
  const rows = step.lines.map((line) => {
    const pt = el("div", { class: "line-pt", hidden: true }, line.pt);
    return { row: el("div", { class: "transcript-row" },
      audioButton(line.ru, "Ouvir esta fala", line.voice),
      el("div", {}, line.speaker ? el("b", { class: "speaker" }, line.speaker) : null, ruText(line.ru), pt)), pt };
  });
  const toggle = el("button", { class: "text-button", type: "button" }, "Mostrar tradução");
  toggle.addEventListener("click", () => {
    showPt = !showPt;
    rows.forEach((r) => { r.pt.hidden = !showPt; });
    toggle.textContent = showPt ? "Esconder tradução" : "Mostrar tradução";
  });
  const all = step.lines.map((l) => ({ text: l.ru, voice: l.voice }));
  return lessonPanel(`${step.phase} · transcrição`,
    el("h2", { class: "listen-title ru" }, step.title),
    el("p", { class: "instruction" }, "Agora ouça de novo acompanhando o texto. Clique em qualquer palavra para ver o verbete e repita as falas mais úteis."),
    el("div", { class: "listen-box" }, linePlayer(all, { label: "Ouvir com texto" }), toggle),
    el("div", { class: "transcript" }, ...rows.map((r) => r.row)),
    nextButton());
}

function renderTranslation(step) {
  const pt = el("div", { class: "translation-pt", hidden: true }, ...step.pt.split("\n\n").map((p) => el("p", {}, p)));
  const toggle = el("button", { class: "btn", type: "button" }, "Mostrar a tradução");
  toggle.addEventListener("click", () => { pt.hidden = !pt.hidden; toggle.textContent = pt.hidden ? "Mostrar a tradução" : "Esconder a tradução"; });
  return lessonPanel(`${step.phase} · releitura`,
    el("h2", { class: "listen-title ru" }, step.title),
    el("p", { class: "instruction" }, "Releia o texto inteiro. Tente entender tudo antes de abrir a tradução; clique nas palavras que não conhece."),
    el("div", { class: "reading-text" }, ...step.ru.split("\n\n").map((p) => el("p", {}, ruText(p, "")))),
    el("div", { class: "next-row left" }, toggle), pt,
    nextButton());
}

function renderCloze(step) {
  const selects = [];
  const text = el("div", { class: "cloze-text" });
  step.parts.forEach((part) => {
    if (typeof part === "string") {
      text.append(ruText(part, ""));
      return;
    }
    const select = el("select", { class: "gap", "aria-label": `Lacuna ${part.gap + 1}` },
      el("option", { value: "" }, "…"), ...part.options.map((o) => el("option", { value: o }, o)));
    select.addEventListener("change", () => { check.disabled = selects.some((s) => !s.value); });
    selects.push(select);
    text.append(select);
  });
  const check = el("button", { class: "btn primary", type: "button", disabled: true }, "Verificar");
  const panel = lessonPanel(step.phase, el("div", { class: "instruction" }, step.instruction),
    step.bank?.length ? el("div", { class: "bank" }, el("small", {}, "Banco de palavras:"), ...step.bank.map((w) => el("span", { class: "chip ru" }, w))) : null,
    text, el("div", { class: "next-row" }, check));
  check.addEventListener("click", async () => {
    check.disabled = true;
    selects.forEach((s) => { s.disabled = true; });
    const result = await submitAnswer(step, selects.map((s) => s.value));
    selects.forEach((s, i) => {
      const ok = result.marks?.[i];
      s.classList.add(ok ? "ok" : "bad");
      if (!ok) s.after(el("span", { class: "gap-fix ru" }, ` ${result.answers[i]}`));
    });
    check.parentElement.remove();
    panel.append(feedbackBox({ ...result, answer: "" }, step), continueRow());
  });
  return panel;
}

function renderMatch(step) {
  const pairs = new Map(); // esquerda -> direita
  let selected = null;
  const colors = ["#2d4fa3", "#b5483f", "#2f7d4f", "#8a6414", "#7a4fb3", "#2a8aa0", "#b3417a", "#5d6b45"];
  const left = step.left.map((t) => el("button", { class: "match-item ru-text", type: "button", dataset: { side: "l", text: t } }, ruText(t, "")));
  const right = step.right.map((t) => el("button", { class: "match-item", type: "button", dataset: { side: "r", text: t } }, /[а-яё]/i.test(t) ? ruText(t, "") : t));
  const check = el("button", { class: "btn primary", type: "button", disabled: true }, "Verificar");
  const paint = () => {
    [...left, ...right].forEach((b) => { b.style.removeProperty("--pair"); b.classList.remove("paired", "selected"); b.querySelector(".badge")?.remove(); });
    [...pairs.entries()].forEach(([l, r], i) => {
      const color = colors[i % colors.length];
      [left.find((b) => b.dataset.text === l), right.find((b) => b.dataset.text === r)].forEach((b) => {
        b.classList.add("paired");
        b.style.setProperty("--pair", color);
        b.prepend(el("span", { class: "badge" }, i + 1));
      });
    });
    if (selected) selected.classList.add("selected");
    check.disabled = pairs.size !== left.length;
  };
  const click = (button) => {
    if (check.dataset.done) return;
    const side = button.dataset.side;
    const text = button.dataset.text;
    if (side === "l" && pairs.has(text)) { pairs.delete(text); selected = null; paint(); return; }
    if (side === "r") {
      const owner = [...pairs.entries()].find(([, r]) => r === text);
      if (owner) { pairs.delete(owner[0]); selected = null; paint(); return; }
    }
    if (!selected || selected.dataset.side === side) { selected = button; paint(); return; }
    const l = side === "l" ? text : selected.dataset.text;
    const r = side === "r" ? text : selected.dataset.text;
    pairs.set(l, r);
    selected = null;
    paint();
  };
  [...left, ...right].forEach((b) => b.addEventListener("click", () => click(b)));
  const panel = lessonPanel(step.phase, el("div", { class: "instruction" }, step.instruction),
    el("p", { class: "hint" }, "Clique num item da esquerda e depois no da direita. Clique de novo para desfazer."),
    el("div", { class: "match-grid" }, el("div", { class: "match-col" }, ...left), el("div", { class: "match-col" }, ...right)),
    el("div", { class: "next-row" }, check));
  check.addEventListener("click", async () => {
    check.dataset.done = "1";
    check.disabled = true;
    const given = [...pairs.entries()].map(([l, r]) => ({ left: l, right: r }));
    const result = await submitAnswer(step, given);
    left.forEach((b) => {
      const ok = result.pairs[b.dataset.text] === pairs.get(b.dataset.text);
      b.classList.add(ok ? "ok" : "bad");
      right.find((r) => r.dataset.text === pairs.get(b.dataset.text))?.classList.add(ok ? "ok" : "bad");
    });
    check.parentElement.remove();
    const box = feedbackBox({ ...result, answer: "" }, step);
    if (!result.correct) {
      box.append(el("ul", { class: "pair-list" }, ...Object.entries(result.pairs).map(([l, r]) => el("li", {}, ruText(l, ""), " = ", /[а-яё]/i.test(r) ? ruText(r, "") : r))));
    }
    panel.append(box, continueRow());
  });
  return panel;
}

function renderShadow(step) {
  const rows = step.lines.map((line) => el("div", { class: "shadow-row" },
    audioButton(line.ru, "Ouvir", line.voice),
    el("div", { class: "shadow-text" }, ruText(line.ru), el("small", {}, line.pt)),
    recorder()));
  const panel = lessonPanel(step.phase, el("div", { class: "instruction" }, step.instruction),
    el("p", { class: "hint" }, "Técnica de sombra: ouça, repita logo em seguida no mesmo ritmo, grave-se e compare. Repita cada frase até soar natural."),
    el("div", { class: "shadow-list" }, ...rows));
  const rate = async (rating) => {
    rating_row.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    await submitAnswer(step, "", { rating });
    panel.append(continueRow());
  };
  const rating_row = el("div", { class: "rating" },
    el("span", { class: "hint" }, "Como soou a sua pronúncia?"),
    el("button", { class: "btn", type: "button", onclick: () => rate(1) }, "Ainda difícil"),
    el("button", { class: "btn", type: "button", onclick: () => rate(2) }, "Quase natural"),
    el("button", { class: "btn primary", type: "button", onclick: () => rate(3) }, "Natural"));
  panel.append(rating_row);
  return panel;
}

function sentences(text) {
  return text.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g)?.map((s) => s.trim()).filter(Boolean) || [text];
}

function renderProduce(step) {
  const speak = step.mode === "speak";
  const area = el("textarea", { class: "produce-area", lang: "ru", rows: speak ? 4 : 9, spellcheck: "false",
    placeholder: speak ? "Opcional: anote aqui palavras-chave antes de falar." : "Escreva aqui em russo." });
  const counter = el("small", { class: "hint" }, "0 palavras");
  area.addEventListener("input", () => {
    const n = (area.value.match(/[\wЁё-]+/g) || []).length;
    counter.textContent = `${n} palavra${n === 1 ? "" : "s"}${step.min_words ? ` · meta: ${step.min_words}` : ""}`;
  });
  const chips = (step.useful || []).map((u) => {
    const chip = el("button", { class: "chip ru", type: "button", title: "Inserir no texto" }, u);
    chip.addEventListener("click", () => {
      const at = area.selectionStart ?? area.value.length;
      area.value = `${area.value.slice(0, at)}${u.replace(/\s*…\s*$/, " ")}${area.value.slice(at)}`;
      area.focus();
      area.dispatchEvent(new Event("input"));
    });
    return chip;
  });
  const done = el("button", { class: "btn primary", type: "button" }, "Terminei: ver o modelo");
  const panel = lessonPanel(step.phase,
    el("div", { class: "instruction" }, step.instruction),
    el("p", { class: "produce-task" }, step.prompt),
    chips.length ? el("div", { class: "useful" }, el("small", {}, "Expressões úteis:"), ...chips) : null,
    speak ? el("div", { class: "speak-box" }, el("p", { class: "hint" }, "Grave a sua fala (ou fale em voz alta) antes de ver o modelo."), recorder()) : null,
    area, counter,
    el("div", { class: "next-row" }, done));
  done.addEventListener("click", () => {
    done.parentElement.remove();
    const modelPt = el("p", { class: "line-pt", hidden: true }, step.model_pt || "");
    const togglePt = el("button", { class: "text-button", type: "button" }, "Mostrar tradução do modelo");
    togglePt.addEventListener("click", () => { modelPt.hidden = !modelPt.hidden; });
    const checks = step.checklist.map((c) => el("label", { class: "check" }, el("input", { type: "checkbox" }), el("span", {}, c)));
    const save = el("button", { class: "btn primary", type: "button" }, "Registrar autoavaliação");
    save.addEventListener("click", async () => {
      save.disabled = true;
      const checked = checks.filter((c) => c.querySelector("input").checked).length;
      await submitAnswer(step, area.value, { checked });
      save.parentElement.replaceWith(el("div", { class: "feedback" }, el("strong", {}, "Registrado."),
        el("p", {}, `Você cumpriu ${checked} de ${checks.length} critérios. O seu texto fica guardado no histórico.`)), continueRow());
    });
    panel.append(
      el("div", { class: "model" }, el("h3", {}, "Um modelo possível"),
        step.model ? linePlayer(sentences(step.model).map((t) => ({ text: t, voice: "f" })), { label: "Ouvir o modelo", compact: true, unit: "frases" }) : null,
        el("div", { class: "model-text" }, ruText(step.model, "")), togglePt, modelPt),
      el("div", { class: "checklist" }, el("h3", {}, "Compare com o seu texto e marque o que você fez"), ...checks),
      el("div", { class: "next-row" }, save));
  });
  return panel;
}

function renderPartEnd(step) {
  const s = state.session;
  const results = [...s.results.values()];
  const graded = results.filter((r) => !["produce", "shadow"].includes(r.step.exercise));
  const right = graded.filter((r) => r.first >= 1).length;
  const actions = el("div", { class: "next-row" },
    el("button", { class: "btn", type: "button", onclick: endSession }, "Voltar ao tema"));
  if (step.next_title) {
    actions.append(el("button", { class: "btn primary", type: "button", "data-autofocus": true,
      onclick: () => startLesson(step.lesson_id, step.part_number) }, `Parte ${step.part_number + 1}: ${step.next_title}`));
  }
  const missed = graded.filter((r) => r.first < 1);
  return el("div", { class: "panel summary" },
    el("h2", {}, step.next_title ? `Parte ${step.part_number} concluída` : "Aula concluída"),
    el("div", { class: "summary-stats" },
      el("div", {}, el("b", {}, graded.length ? `${percent(right, graded.length)}%` : "—"), el("span", {}, "de acerto na primeira tentativa")),
      el("div", {}, el("b", {}, graded.length), el("span", {}, "exercícios avaliados"))),
    el("p", { class: "hint" }, step.next_title
      ? "Os itens desta parte entram na revisão espaçada do tema. Faça a próxima parte agora ou mais tarde: o progresso fica salvo."
      : "Parabéns! Todos os itens da aula entram na revisão espaçada. Volte ao tema e use «Revisar» nos próximos dias."),
    missed.length ? el("div", {}, el("h3", {}, "Para revisar com calma"),
      el("div", { class: "summary-list" }, ...missed.slice(0, 10).map((r) => el("div", {}, ruText(r.label, ""), el("small", { class: "hint" }, r.step.phase || ""))))) : null,
    actions);
}

// ------------------------------------------------------------------ bloco da aula na gaveta
function nextPart(module) {
  const open = module.parts.find((p) => p.seen < p.items);
  return open ? open.index : 0;
}

function lessonModuleCard(theme, module) {
  const tiles = module.parts.map((part) => el("button", {
    class: `part-tile${part.seen >= part.items ? " done" : part.seen ? " started" : ""}`, type: "button",
    onclick: () => startLesson(module.id, part.index), title: part.goal,
  },
  el("span", { class: "part-num" }, `Parte ${part.index + 1}`),
  el("span", { class: "part-name" }, part.title),
  el("span", { class: "part-kinds" }, part.kinds.join(" · ")),
  meter(part.seen, part.mastered, part.items),
  el("span", { class: "part-count" }, part.seen >= part.items ? "concluída" : `${part.seen}/${part.items}`)));
  const objectives = el("details", { class: "objectives-toggle" }, el("summary", {}, "Objetivos e foco gramatical"),
    el("ul", {}, ...module.objectives.map((o) => el("li", {}, o))),
    module.grammar_focus ? el("p", { class: "hint" }, "Foco gramatical: ", ruText(module.grammar_focus, "")) : null);
  return el("div", { class: "module" },
    el("div", { class: "module-head" },
      el("div", {},
        el("span", { class: "module-label" }, "Aula temática"),
        el("h3", { class: "ru" }, module.title),
        el("span", { class: "module-sub" }, [module.title_pt, module.level, module.minutes ? `cerca de ${module.minutes} min` : ""].filter(Boolean).join(" · "))),
      el("button", { class: "btn primary", type: "button", onclick: () => startLesson(module.id, nextPart(module)) },
        module.seen ? (module.seen >= module.items ? "Refazer a aula" : `Continuar: parte ${nextPart(module) + 1}`) : "Começar a aula")),
    el("div", { class: "part-row" }, ...tiles),
    objectives);
}
