function readPreference(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
}
function savePreference(key, value) {
  try { localStorage.setItem(key, value); } catch (_) {}
}

const state = {
  bootstrap: null,
  summary: null,
  sessionId: null,
  // Sem seletor de consulta: toda resposta conta como recuperação sem consulta (SC).
  consultation: 'SC',
  queue: [],
  current: 0,
  sessionMode: 'study',
  selectedAnswer: '',
  builtTokens: [],
  startedAt: 0,
  results: [],
  reportExercise: null,
  speakingElement: null,
  sessionHost: '#sessionArea',
  morphologyData: null,
  prefixData: null,
  vocabData: null,
  vocabLesson: null,
  vocabRetries: {},
  sessionKey: null,
  sessionKind: '',
  sessionTitle: '',
  sessionMeta: {},
  itemStatus: [],
  answeredCurrent: false,
  sessionElapsed: 0,
  sessionClock: 0,
  activeSessions: [],
  saveChain: Promise.resolve(),
  // Foco no russo: os outros cursos continuam no servidor, mas não aparecem na interface.
  courseId: 'russian',
  lesson: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const baseViewMeta = {
  home: ['ПРОГРАММА', 'Aulas'],
  lesson: ['УРОК', 'Aula'],
  practice: ['ПРАКТИКА', 'Praticar'],
  study: ['ПРАКТИКА', 'Praticar'],
  vocab: ['ЛЕКСИКА В ДИАЛОГЕ', 'Vocabulário em diálogo'],
  errors: ['РАБОТА НАД ОШИБКАМИ', 'Caderno de erros'],
  reference: ['УПРАВЛЕНИЕ', 'Referência'],
  morphology: ['КАРТА ОКОНЧАНИЙ', 'Terminações e léxico B2'],
  prefixes: ['ГЛАГОЛЬНЫЕ ПРИСТАВКИ', 'Verbos com prefixo'],
  progress: ['ПРОГРЕСС', 'Progresso'],
};
// Telas que pertencem a "Praticar": o menu lateral continua marcando Praticar e aparece "← Praticar".
const PRACTICE_VIEWS = new Set(['study', 'vocab', 'errors', 'morphology', 'prefixes']);

const courseConfigs = {
  russian: {
    brand: 'Русский тренажёр', level: 'ТРКИ-II · B2', mark: 'Я', title: 'Russo · ТРКИ-II',
    eyebrow: 'РУССКИЙ · B2', heroKicker: 'СЕГОДНЯ', heroTitle: 'Transforme regência em reflexo.',
    heroCopy: 'Reconhecer o caso é só o começo. O objetivo é recuperar a construção e produzir a terminação sem traduzir mentalmente.',
    visual: [['Д', 'дательный'], ['Т', 'творительный'], ['Р', 'родительный']],
    primary: 'Fazer diagnóstico', startLabel: 'Diagnóstico inicial', emptyFocus: 'diagnóstico inicial',
    pathTitle: 'Percorra as unidades em ordem.', pathCopy: 'Conclua cada unidade para desbloquear a próxima. Revisão e itens difíceis continuam livres, sem depender da trilha.',
    referenceTitle: 'Aprenda a construção inteira.', referenceCopy: 'Verbo ou expressão + preposição + pergunta russa. A tradução vem por último.',
  },
  romanian: {
    brand: 'Română pas cu pas', level: 'CEFR · A1', mark: 'Ă', title: 'Romeno · A1',
    eyebrow: 'ROMÂNĂ · A1', heroKicker: 'ASTĂZI · PRIMII PAȘI', heroTitle: 'Comece a conversar desde a primeira aula.',
    heroCopy: 'Cumprimentos, cortesia e pronúncia entram juntos em diálogos curtos. Você ouve, reconhece e produz as mesmas estruturas em situações reais.',
    visual: [['B', 'Bună ziua'], ['Ă', 'mulțumesc'], ['Ț', 'pronunție']],
    primary: 'Começar Unidade 1', startLabel: 'Unidade 1 · Salut!', emptyFocus: 'cumprimentos e cortesia',
    pathTitle: 'Seu percurso começa no A1.', pathCopy: 'Cada unidade combina vocabulário frequente, pronúncia, compreensão e produção desde o início.',
    referenceTitle: 'Guarde frases que resolvem situações.', referenceCopy: 'Aprenda a expressão completa com contexto e registro — formal ou informal.',
  },
  kazakh: {
    brand: 'Қазақ тілі', level: 'Curso em preparação', mark: 'Қ', title: 'Cazaque',
    eyebrow: 'ҚАЗАҚ ТІЛІ', heroKicker: 'ЖАҚЫНДА', heroTitle: 'O espaço do curso cazaque está pronto.',
    heroCopy: 'A interface, o progresso e o áudio serão independentes. As unidades serão adicionadas a partir dos materiais cazaques disponíveis, sem misturar o percurso russo.',
    visual: [['Қ', 'қазақ'], ['Ә', 'әліпби'], ['Ө', 'дыбыс']],
    primary: 'Curso em preparação', startLabel: 'Conteúdo em preparação', emptyFocus: 'curso em preparação',
    pathTitle: 'Curso em preparação.', pathCopy: 'Nenhuma unidade foi publicada ainda. O seletor já mantém este espaço separado dos outros cursos.',
    referenceTitle: 'Referência em preparação.', referenceCopy: 'As expressões aparecerão aqui quando a primeira unidade for criada.',
  },
};

function currentConfig() {
  return courseConfigs[state.courseId] || courseConfigs.russian;
}

function courseUnits() {
  return (state.bootstrap?.units || []).filter(unit => (unit.course_id || 'russian') === state.courseId);
}

function currentViewMeta(name) {
  const base = baseViewMeta[name] || ['', name];
  return [`РУССКИЙ · B2 · ${base[0]}`, base[1]];
}

const typeLabels = {
  choice: 'MÚLTIPLA ESCOLHA',
  input: 'PRODUÇÃO ATIVA',
  correction: 'CORREÇÃO DE ERRO',
  sentence_order: 'MONTAGEM DE FRASE',
  flashcard: 'FLASHCARD',
  open_text: 'PRODUÇÃO ESCRITA',
  match_pairs: 'RELACIONAR PARES',
  reading: 'LEITURA',
  listening: 'AUDIÇÃO',
  dialogue: 'DIÁLOGO',
  vocab_card: 'APRESENTAÇÃO',
  dialogue_review: 'RE-ESCUTA',
};

// Tipos só de apresentação: não vão ao servidor nem contam no resultado.
const UNGRADED = new Set(['vocab_card', 'dialogue_review']);
const VOICE_NAMES = { f: 'voz feminina', m: 'voz masculina', f2: 'voz feminina 2', m2: 'voz masculina 2' };

const errorLabels = {
  regencia: 'Regência/preposição',
  terminacao: 'Terminação',
  vocabulario: 'Vocabulário/significado',
  aspecto: 'Aspecto',
  gramatica: 'Gramática/construção',
  ortografia: 'Ortografia/diacrítico',
  pronuncia: 'Pronúncia/listening',
  digitacao: 'Digitação',
  nao_sei: 'Não sei',
};

function activeErrorLabels() {
  if (state.courseId === 'russian') {
    return Object.fromEntries(['regencia', 'terminacao', 'vocabulario', 'aspecto', 'digitacao', 'nao_sei'].map(key => [key, errorLabels[key]]));
  }
  return Object.fromEntries(['gramatica', 'ortografia', 'vocabulario', 'pronuncia', 'digitacao', 'nao_sei'].map(key => [key, errorLabels[key]]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Erro inesperado');
  return data;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function shuffle(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 2600);
}

function setView(name) {
  if (!$(`#${name}View`)) name = 'home';
  $$('.view').forEach(view => view.classList.remove('active'));
  $(`#${name}View`).classList.add('active');
  const navName = PRACTICE_VIEWS.has(name) ? 'practice' : name === 'lesson' ? 'home' : name;
  $$('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.view === navName));
  $('#backToPractice').classList.toggle('hidden', !PRACTICE_VIEWS.has(name) || name === 'study');
  const meta = currentViewMeta(name);
  $('#viewEyebrow').textContent = meta[0];
  $('#viewTitle').textContent = name === 'lesson' && state.lesson ? lessonHeading(state.lesson.unit) : meta[1];
  $('.sidebar').classList.remove('open');
  window.scrollTo({ top: 0 });
  if (name === 'errors') renderErrors();
  if (name === 'reference') renderReference();
  if (name === 'morphology') loadMorphology();
  if (name === 'prefixes') loadPrefixes();
  if (name === 'vocab') loadVocab();
  if (name === 'progress') loadPendingWriting();
  if (name === 'practice') renderPractice();
  if (name === 'home' && state.bootstrap) loadActiveSessions();
}

async function loadMorphology() {
  try {
    state.morphologyData = await api('/api/morphology/bootstrap');
    renderMorphologyMetrics();
  } catch (error) {
    $('#morphStatus').textContent = error.message;
  }
}

function renderMorphologyMetrics() {
  if (!state.morphologyData) return;
  const inventory = state.morphologyData.inventory || {};
  const coverage = state.morphologyData.coverage || {};
  $('#coveragePercent').textContent = `${coverage.seen_percent || 0}%`;
  $('#morphMetrics').innerHTML = [
    ['Inventário B2', Number(inventory.unique_lemmas || 0).toLocaleString('pt-BR'), 'lemas únicos extraídos'],
    ['Jogos de flexão', Number(inventory.morphology_cards || 0).toLocaleString('pt-BR'), `${Number(inventory.morphology_lemmas || 0).toLocaleString('pt-BR')} lemas declináveis`],
    ['Já vistos', Number(coverage.seen || 0).toLocaleString('pt-BR'), `${coverage.seen_percent || 0}% do inventário`],
    ['Dominados', Number(coverage.mastered || 0).toLocaleString('pt-BR'), coverage.mastery_rule || '2 acertos exatos SC'],
  ].map(([label, value, note]) => `<article class="morph-stat"><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b><span>${escapeHtml(note)}</span></article>`).join('');
}

function syncMorphFilters() {
  const vocabulary = $('#morphKind').value === 'vocabulary';
  $('#morphCase').disabled = vocabulary;
  $('#morphNumber').disabled = vocabulary;
  $('#morphResponse').disabled = vocabulary;
  if (vocabulary) $('#morphResponse').value = 'choice';
  [...$('#morphPos').options].forEach(option => {
    if (option.value === 'verb') option.disabled = !vocabulary;
    if (vocabulary && option.value === 'adjective') option.disabled = false;
  });
  if (!vocabulary && $('#morphPos').value === 'verb') $('#morphPos').value = '';
}

async function startMorphologyGame() {
  const morphKind = $('#morphKind').value;
  if (await resolveResume(`morph:${morphKind}`) !== 'new') return;
  const params = new URLSearchParams({
    kind: $('#morphKind').value,
    response: $('#morphResponse').value,
    pos: $('#morphPos').value,
    case: $('#morphCase').value,
    number: $('#morphNumber').value,
    limit: $('#morphLimit').value,
    unseen: $('#morphUnseen').checked ? '1' : '0',
  });
  $('#morphStatus').textContent = 'Sorteando palavras do inventário…';
  try {
    const data = await api(`/api/morphology/questions?${params}`);
    if (!data.exercises.length) {
      $('#morphStatus').textContent = 'Não há lemas inéditos nesse filtro. Desmarque “Só lemas inéditos” ou escolha outro grupo.';
      return;
    }
    state.queue = data.exercises;
    state.current = 0;
    state.results = [];
    state.sessionMode = $('#morphKind').value === 'vocabulary' ? 'lexical_coverage' : 'morphology_game';
    state.sessionHost = '#morphologyGameArea';
    beginTracking({ key: `morph:${morphKind}`, kind: 'morph', title: morphKind === 'vocabulary' ? 'Terminações · cobertura lexical' : 'Terminações · jogo de flexão' });
    $('#morphologyContent').classList.add('hidden');
    $('#morphologyGameArea').classList.remove('hidden');
    renderExercise();
  } catch (error) {
    $('#morphStatus').textContent = error.message;
  }
}

async function loadPrefixes() {
  try {
    state.prefixData = await api('/api/prefixes/bootstrap');
    renderPrefixModule();
  } catch (error) {
    $('#prefixStatus').textContent = error.message;
  }
}

function renderPrefixModule() {
  const data = state.prefixData;
  if (!data) return;
  const progress = data.progress || { stages: {}, total: 0, cleared: 0 };
  const percent = progress.total ? Math.round(100 * progress.cleared / progress.total) : 0;
  $('#prefixMasteryPercent').textContent = `${percent}%`;

  $('#prefixIntro').innerHTML = (data.intro || []).map(block => `
    <article class="panel prefix-lesson">
      <h3>${escapeHtml(block.title || '')}</h3>
      ${(block.paragraphs || []).map(p => `<p>${interactiveRussianText(p)}</p>`).join('')}
    </article>`).join('');

  $('#prefixStageGrid').innerHTML = (data.stages || []).map(stage => {
    const st = (progress.stages || {})[stage.id] || { total: stage.count || 0, cleared: 0 };
    const done = st.total && st.cleared >= st.total;
    return `<button type="button" class="prefix-stage${done ? ' done' : ''}${stage.id === 'contrast' ? ' contrast' : ''}" data-stage="${escapeHtml(stage.id)}">
      <b>${escapeHtml(stage.prefix)}</b>
      <span>${escapeHtml(stage.meaning || '')}</span>
      ${stage.hint ? `<em>${escapeHtml(stage.hint)}</em>` : ''}
      <small>${st.cleared}/${st.total || stage.count || 0} dominados</small>
    </button>`;
  }).join('');
  $$('#prefixStageGrid .prefix-stage').forEach(button =>
    button.addEventListener('click', () => startPrefixSession(button.dataset.stage)));
  bindInteractiveWords();
}

async function startPrefixSession(stage) {
  if (await resolveResume(`prefix:${stage}`) !== 'new') return;
  const limit = $('#prefixLimit').value || '16';
  $('#prefixStatus').textContent = 'Sorteando frases…';
  try {
    const data = await api(`/api/prefixes/questions?stage=${encodeURIComponent(stage)}&limit=${encodeURIComponent(limit)}`);
    if (!data.exercises.length) {
      $('#prefixStatus').textContent = 'Nenhuma frase encontrada para esse prefixo.';
      return;
    }
    state.queue = data.exercises;
    state.current = 0;
    state.results = [];
    state.sessionMode = 'prefix_practice';
    state.sessionHost = '#prefixGameArea';
    const stageInfo = (state.prefixData?.stages || []).find(item => item.id === stage);
    beginTracking({ key: `prefix:${stage}`, kind: 'prefix', title: `Prefixos · ${stage === 'all' ? 'todos os prefixos' : (stageInfo?.prefix || stage)}` });
    $('#prefixStatus').textContent = '';
    $('#prefixesContent').classList.add('hidden');
    $('#prefixGameArea').classList.remove('hidden');
    renderExercise();
  } catch (error) {
    $('#prefixStatus').textContent = error.message;
  }
}

// ---------------------------------------------------------------------------
// Vocabulário · «Лексика в диалоге»
// ---------------------------------------------------------------------------

async function loadVocab() {
  const token = (state.vocabLoadToken || 0) + 1;
  state.vocabLoadToken = token;
  try {
    const data = await api('/api/vocab/bootstrap');
    if (token !== state.vocabLoadToken || state.queue.length && state.sessionMode === 'vocab_lesson') return;
    state.vocabData = data;
    renderVocabModule();
    if (state.vocabLesson) openVocabLesson(state.vocabLesson.id, false);
  } catch (error) {
    $('#vocabStatus').textContent = error.message;
  }
}

function unitNumberById() {
  return unitDisplayNumbers(courseUnits());
}

function renderVocabModule() {
  const data = state.vocabData;
  if (!data) return;
  const progress = data.progress || {};
  const lessons = data.lessons || [];
  const itemsTotal = lessons.reduce((sum, lesson) => sum + (progress[lesson.id]?.items_total || 0), 0);
  const itemsFirm = lessons.reduce((sum, lesson) => sum + (progress[lesson.id]?.items_firm || 0), 0);
  const started = lessons.filter(lesson => (progress[lesson.id]?.attempted || 0) > 0).length;
  const graded = lessons.reduce((sum, lesson) => sum + (progress[lesson.id]?.total || 0), 0);
  const cleared = lessons.reduce((sum, lesson) => sum + (progress[lesson.id]?.cleared || 0), 0);
  $('#vocabFirmPercent').textContent = `${itemsTotal ? Math.round(100 * itemsFirm / itemsTotal) : 0}%`;
  $('#vocabMetrics').innerHTML = [
    ['Lições', lessons.length, `${started} iniciadas`],
    ['Construções', itemsTotal, `${itemsFirm} firmes (forma + lacuna + montagem)`],
    ['Tarefas corrigidas', graded, `${cleared} dominadas`],
    ['Léxico TRKI-II visto', `${data.coverage?.seen_percent || 0}%`, `${data.coverage?.seen || 0} lemas`],
  ].map(([label, value, note]) => `<article class="morph-stat"><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b><span>${escapeHtml(note)}</span></article>`).join('');
  const numbers = unitNumberById();
  $('#vocabCount').textContent = `${lessons.length} lições · ${itemsTotal} construções`;
  $('#vocabGrid').innerHTML = lessons.map(lesson => {
    const p = progress[lesson.id] || { total: lesson.graded_count, cleared: 0, items_firm: 0, items_total: lesson.item_heads.length };
    const percent = p.total ? Math.round(100 * p.cleared / p.total) : 0;
    const number = numbers[lesson.unit_id];
    const active = state.vocabLesson?.id === lesson.id;
    const vocabSaved = (state.activeSessions || []).filter(session => session.key.startsWith(`vocab:${lesson.id}:`));
    return `<button type="button" class="vocab-lesson-card${active ? ' active' : ''}${p.items_firm && p.items_firm >= p.items_total ? ' done' : ''}" data-lesson="${escapeHtml(lesson.id)}">
      <span class="unit-index">${number ? `AULA ${String(number).padStart(2, '0')}` : 'LIÇÃO'} · ${escapeHtml(lesson.theme)}</span>
      <b>${escapeHtml(lesson.title)}</b>
      <span class="vocab-heads">${lesson.item_heads.slice(0, 8).map(head => `<i>${escapeHtml(head)}</i>`).join('')}</span>
      <span class="vocab-bar"><i style="width:${percent}%"></i></span>
      ${vocabSaved.length ? `<span class="vocab-session-note">▶ ${vocabSaved.length === 1 ? 'sessão em andamento' : `${vocabSaved.length} sessões em andamento`}</span>` : ''}
      <small>${p.items_firm}/${p.items_total} construções firmes · ${p.cleared}/${p.total} tarefas</small>
    </button>`;
  }).join('') || '<div class="empty-state">Nenhuma lição encontrada em data/vocab_lessons.</div>';
  $$('#vocabGrid .vocab-lesson-card').forEach(button => button.addEventListener('click', () => openVocabLesson(button.dataset.lesson)));
}

async function openVocabLesson(lessonId, scroll = true) {
  const token = (state.vocabOpenToken || 0) + 1;
  state.vocabOpenToken = token;
  state.vocabLesson = { id: lessonId };
  const detail = $('#vocabLessonDetail');
  detail.setAttribute('aria-busy', 'true');
  $$('.vocab-part', detail).forEach(button => button.disabled = true);
  let data;
  try {
    data = await api(`/api/vocab/lesson?id=${encodeURIComponent(lessonId)}`);
  } catch (error) {
    if (token === state.vocabOpenToken) {
      detail.setAttribute('aria-busy', 'false');
      $$('.vocab-part', detail).forEach(button => button.disabled = false);
      showToast(error.message);
    }
    return;
  }
  if (token !== state.vocabOpenToken || state.queue.length && state.sessionMode === 'vocab_lesson') return;
  detail.setAttribute('aria-busy', 'false');
  const lesson = data.lesson;
  const p = data.progress || {};
  state.vocabLesson = lesson;
  $$('#vocabGrid .vocab-lesson-card').forEach(card => card.classList.toggle('active', card.dataset.lesson === lessonId));
  const unit = courseUnits().find(item => item.id === lesson.unit_id);
  const number = unitNumberById()[lesson.unit_id];
  const partButtons = Object.entries(lesson.parts).map(([key, label]) => `<button type="button" class="vocab-part" data-part="${key}">
      <b>Parte ${key}</b><span>${escapeHtml(label)}</span><small>${lesson.screens[key] || 0} telas</small>
    </button>`).join('');
  const glossary = lesson.items.map(item => `<tr>
      <td><button type="button" class="mini-speak" data-text="${escapeHtml(item.chunk)}" title="Ouvir">🔊</button></td>
      <td><b>${interactiveRussianText(item.head)}</b><small>${escapeHtml(item.regency)}</small></td>
      <td>${escapeHtml(item.pt)}</td>
      <td>${interactiveRussianText(item.chunk)}<small>${escapeHtml(item.chunk_pt)}</small></td>
    </tr>`).join('');
  const host = $('#vocabLessonDetail');
  host.innerHTML = `<article class="panel vocab-detail" data-lesson="${escapeHtml(lesson.id)}">
    <div class="vocab-detail-head">
      <div>
        <p class="eyebrow">${number ? `AULA ${number} · ` : ''}${escapeHtml(lesson.theme)}</p>
        <h2>${escapeHtml(lesson.title)}</h2>
        <p class="muted">${escapeHtml(lesson.description)}</p>
        ${unit ? `<p class="source-note">Aula correspondente: ${escapeHtml(unit.title)}</p>` : ''}
      </div>
      <div class="vocab-detail-score"><strong>${p.items_firm || 0}/${p.items_total || lesson.items.length}</strong><span>construções firmes</span><small>${p.cleared || 0}/${p.total || lesson.graded_count} tarefas dominadas</small></div>
    </div>
    <div class="vocab-parts">
      <button type="button" class="vocab-part full" data-part="all"><b>Lição completa</b><span>as três partes em sequência</span><small>${Object.values(lesson.screens).reduce((a, b) => a + b, 0)} telas</small></button>
      ${partButtons}
    </div>
    <details class="vocab-scene">
      <summary>Cena: ${escapeHtml(lesson.dialogue_title)} — ouvir fora da lição</summary>
      <p class="muted">${escapeHtml(lesson.setting)}</p>
      ${dialogueBlockMarkup(lesson.lines, { transcript: false, highlights: lesson.highlights })}
    </details>
    <details class="vocab-registry">
      <summary>Registro pergunta por pergunta</summary>
      <div class="vocab-map-host"></div>
    </details>
    <details class="vocab-glossary">
      <summary>Glossário das oito construções</summary>
      <p class="muted">Consultar antes da Parte 1 tira o efeito do pré-teste. Use depois, para revisar.</p>
      <div class="table-scroll"><table class="ending-table vocab-table">
        <thead><tr><th></th><th>Construção</th><th>Sentido</th><th>Colocação</th></tr></thead>
        <tbody>${glossary}</tbody>
      </table></div>
    </details>
  </article>`;
  host.classList.remove('hidden');
  $$('.vocab-part', host).forEach(button => button.addEventListener('click', () => startVocabSession(lesson.id, button.dataset.part)));
  markVocabParts();
  const registry = $('.vocab-registry', host);
  registry.addEventListener('toggle', () => {
    if (registry.open) loadQuestionMap($('.vocab-map-host', registry), `vocab:${lesson.id}`, lesson.parts, ({ id, part }) => startVocabSession(lesson.id, part, { jumpId: id }));
  });
  $$('.mini-speak', host).forEach(button => button.addEventListener('click', () => speakText(button.dataset.text, button)));
  bindDialogueBlock(host, lesson.lines);
  bindInteractiveWords();
  if (scroll) host.scrollIntoView({ behavior: 'auto', block: 'start' });
}

async function startVocabSession(lessonId, part = 'all', opts = {}) {
  if (state.vocabStarting) return;
  const vocabKey = `vocab:${lessonId}:${part}`;
  if (await resolveResume(vocabKey, opts) !== 'new') return;
  state.vocabStarting = true;
  $$('.vocab-part').forEach(button => button.disabled = true);
  let data;
  try {
    data = await api(`/api/vocab/session?id=${encodeURIComponent(lessonId)}&part=${encodeURIComponent(part)}`);
  } catch (error) {
    showToast(error.message);
    return;
  } finally {
    state.vocabStarting = false;
    $$('.vocab-part').forEach(button => button.disabled = false);
  }
  if (!data.exercises.length) { showToast('Parte sem exercícios.'); return; }
  stopAllAudio();
  state.queue = data.exercises;
  state.current = 0;
  state.results = [];
  state.vocabRetries = {};
  state.vocabPart = part;
  state.sessionMode = 'vocab_lesson';
  state.sessionHost = '#vocabGameArea';
  const lessonInfo = (state.vocabData?.lessons || []).find(item => item.id === lessonId);
  beginTracking({
    key: vocabKey, kind: 'vocab', meta: { lessonId },
    title: `Vocabulário · ${lessonInfo?.title || lessonId} · ${part === 'all' ? 'lição completa' : `parte ${part}`}`,
  });
  const vocabJump = opts.jumpId ? state.queue.findIndex(item => item.id === opts.jumpId) : -1;
  if (vocabJump >= 0) state.current = vocabJump;
  $('#vocabContent').classList.add('hidden');
  $('#vocabGameArea').classList.remove('hidden');
  renderExercise();
  // Aquece o cache de áudio das falas do diálogo enquanto o aluno lê a instrução.
  const lines = data.exercises.find(ex => ex.lines)?.lines || [];
  warmDialogueAudio(lines);
}

function goToVocabLesson(lessonId) {
  setView('vocab');
  state.vocabLesson = { id: lessonId };
}

// ---------------------------- player de diálogo ----------------------------

function warmDialogueAudio(lines) {
  state.warmAudioController?.abort();
  const controller = new AbortController();
  state.warmAudioController = controller;
  // Sequencial: o servidor sintetiza uma fala por vez; assim a primeira
  // reprodução não espera o diálogo inteiro.
  (async () => {
    for (const line of lines) {
      if (controller.signal.aborted) return;
      try {
        const response = await fetch(ttsUrl(line.ru, line.voice), { signal: controller.signal });
        if (!response.ok) return;
        await response.arrayBuffer();
      } catch (error) { return; }
    }
  })();
}

function highlightRussian(text, stems = []) {
  const html = interactiveRussianText(text);
  if (!stems.length) return html;
  return html.replace(/<button type="button" class="word-button" data-word="([^"]+)"/g, (match, word) => {
    const normalized = word.toLowerCase().replace(/ё/g, 'е');
    return stems.some(stem => normalized.startsWith(stem))
      ? match.replace('class="word-button"', 'class="word-button target-word"')
      : match;
  });
}

function dialogueBlockMarkup(lines, { transcript = true, highlights = [], allowText = true } = {}) {
  const speakers = [...new Set(lines.map(line => line.speaker))];
  return `<div class="dialogue-block">
    <div class="dialogue-player">
      <button type="button" class="primary dlg-play">▶ Ouvir o diálogo</button>
      <button type="button" class="secondary dlg-slow">Devagar</button>
      <button type="button" class="secondary dlg-stop hidden">■ Parar</button>
      <span class="muted dlg-status">${speakers.map(name => `<span class="dlg-chip v-${escapeHtml(lines.find(line => line.speaker === name).voice)}">${escapeHtml(name)}</span>`).join(' ')} · <span class="dlg-state" role="status" aria-live="polite">Parado</span> · <span class="dlg-count">0 audições completas</span></span>
    </div>
    <div class="dialogue-transcript${transcript ? '' : ' hidden'}">
      ${lines.map((line, index) => `<div class="dlg-line" data-index="${index}">
        <button type="button" class="dlg-line-play" title="Ouvir esta fala" aria-label="Ouvir esta fala">🔊</button>
        <b class="dlg-speaker v-${escapeHtml(line.voice)}">${escapeHtml(line.speaker)}</b>
        <span class="dlg-ru">${highlightRussian(line.ru, highlights)}</span>
        <span class="dlg-pt hidden">${escapeHtml(line.pt || '')}</span>
      </div>`).join('')}
    </div>
    <div class="dialogue-tools">
      ${transcript || !allowText ? '' : '<button type="button" class="ghost-button dlg-show-text">Mostrar texto</button>'}
      <button type="button" class="ghost-button dlg-toggle-pt${transcript ? '' : ' hidden'}">Mostrar tradução</button>
    </div>
  </div>`;
}

class DialoguePlayer {
  constructor(lines, root) {
    this.lines = lines;
    this.root = root;
    this.audio = new Audio();
    this.audio.preload = 'auto';
    this.token = 0;
    this.plays = 0;
    this.playing = false;
    this.status = 'Parado';
    this.cancelPending = null;
  }

  async play(rate = 1, from = 0, only = null) {
    stopAllAudio();
    state.dialoguePlayer = this;
    const token = ++this.token;
    this.playing = true;
    this.status = 'Carregando áudio…';
    this.sync();
    const indexes = only === null ? this.lines.map((_, index) => index).slice(from) : [only];
    let completed = true;
    for (const index of indexes) {
      if (token !== this.token) return;
      const line = this.lines[index];
      this.mark(index);
      try {
        await this.playOne(line, rate, token);
      } catch (error) {
        completed = false;
        this.status = 'Áudio indisponível';
        showToast('Não foi possível gerar o áudio do diálogo. O edge-tts precisa de internet na primeira vez.');
        break;
      }
      if (token !== this.token) return;
      await new Promise(resolve => setTimeout(resolve, rate < 1 ? 650 : 380));
    }
    if (token === this.token) {
      this.playing = false;
      if (completed && only === null) this.plays += 1;
      if (completed) this.status = 'Parado';
      this.mark(-1);
      this.sync();
    }
  }

  playOne(line, rate, token) {
    return new Promise((resolve, reject) => {
      this.cancelPending = resolve;
      this.status = 'Carregando áudio…';
      this.sync();
      this.audio.onplaying = () => {
        if (token !== this.token) return;
        this.status = 'Tocando';
        this.sync();
      };
      this.audio.onwaiting = () => { this.status = 'Carregando áudio…'; this.sync(); };
      this.audio.onended = () => { this.cancelPending = null; resolve(); };
      this.audio.onerror = () => reject(new Error('audio'));
      this.audio.src = ttsUrl(line.ru, line.voice);
      this.audio.playbackRate = rate;
      const promise = this.audio.play();
      if (promise) promise.catch(error => { if (token === this.token) reject(error); else resolve(); });
    });
  }

  stop() {
    this.token += 1;
    this.audio.pause();
    this.cancelPending?.();
    this.cancelPending = null;
    this.status = 'Parado';
    this.playing = false;
    this.mark(-1);
    this.sync();
  }

  mark(index) {
    $$('.dlg-line', this.root).forEach(line => line.classList.toggle('playing', Number(line.dataset.index) === index));
  }

  sync() {
    const count = $('.dlg-count', this.root);
    if (count) count.textContent = `${this.plays} ${this.plays === 1 ? 'audição completa' : 'audições completas'}`;
    const status = $('.dlg-state', this.root);
    if (status) status.textContent = this.status;
    $('.dlg-slow', this.root).disabled = this.playing;
    $('.dlg-stop', this.root)?.classList.toggle('hidden', !this.playing);
    $('.dlg-play', this.root)?.classList.toggle('hidden', this.playing);
  }
}

function bindDialogueBlock(root, lines) {
  const block = $('.dialogue-block', root);
  if (!block) return null;
  const player = new DialoguePlayer(lines, block);
  $('.dlg-play', block).addEventListener('click', () => player.play(1));
  $('.dlg-slow', block).addEventListener('click', () => player.play(0.8));
  $('.dlg-stop', block).addEventListener('click', () => player.stop());
  $$('.dlg-line-play', block).forEach(button => button.addEventListener('click', () => {
    player.play(1, 0, Number(button.closest('.dlg-line').dataset.index));
  }));
  $('.dlg-show-text', block)?.addEventListener('click', event => {
    $('.dialogue-transcript', block).classList.remove('hidden');
    $('.dlg-toggle-pt', block).classList.remove('hidden');
    event.currentTarget.remove();
  });
  $('.dlg-toggle-pt', block)?.addEventListener('click', event => {
    const hidden = $$('.dlg-pt', block).some(item => item.classList.contains('hidden'));
    $$('.dlg-pt', block).forEach(item => item.classList.toggle('hidden', !hidden));
    event.currentTarget.textContent = hidden ? 'Ocultar tradução' : 'Mostrar tradução';
  });
  return player;
}

// ------------------------ tipos de exercício novos ------------------------

function vocabCardMarkup(ex) {
  return `<div class="vocab-card">
    <div class="vc-head">
      <button type="button" class="vc-speak" data-text="${escapeHtml(ex.head)}" title="Ouvir">🔊</button>
      <h2>${interactiveRussianText(ex.head)}</h2>
      ${ex.case ? `<span class="vc-case">${escapeHtml(ex.case)}</span>` : ''}
    </div>
    <p class="vc-meaning">${escapeHtml(ex.meaning)}</p>
    ${ex.regency ? `<p class="vc-regency">${interactiveRussianText(ex.regency)}</p>` : ''}
    <div class="vc-row vc-chunk">
      <button type="button" class="vc-speak" data-text="${escapeHtml(ex.chunk)}" data-autoplay="1" title="Ouvir">🔊</button>
      <div><b>${interactiveRussianText(ex.chunk)}</b><span>${escapeHtml(ex.chunk_pt)}</span></div>
    </div>
    <div class="vc-row vc-example">
      <button type="button" class="vc-speak" data-text="${escapeHtml(ex.example_ru)}" data-voice="m" title="Ouvir">🔊</button>
      <div><b>${interactiveRussianText(ex.example_ru)}</b><span>${escapeHtml(ex.example_pt)}</span></div>
    </div>
    ${ex.trap ? `<div class="vc-trap"><strong>Armadilha para quem fala português</strong><p>${interactiveRussianText(ex.trap)}</p></div>` : ''}
  </div>
  <div class="continue-row"><button class="primary continue-ungraded">Continuar</button></div>`;
}

function queueVocabRetry(ex, result) {
  if (state.sessionMode !== 'vocab_lesson' || result.is_correct !== false || UNGRADED.has(ex.type) || ex.type === 'open_text') return false;
  const baseId = ex.id;
  const count = state.vocabRetries[baseId] || 0;
  // Perguntas sobre o diálogo voltam uma vez (segunda escuta); construções, até duas.
  if (count >= (ex.type === 'dialogue' ? 1 : 2)) return false;
  state.vocabRetries[baseId] = count + 1;
  const clone = { ...ex, retry: true, phase: '↻ RECUPERAR DE NOVO' };
  if (Array.isArray(clone.options)) clone.options = shuffle(clone.options);
  // Reaprendizagem sucessiva: o item volta depois de pelo menos 4 outras telas,
  // mas sempre antes da re-escuta final e da produção escrita.
  const closingIndex = state.queue.findIndex((item, index) => index > state.current && (UNGRADED.has(item.type) && item.type === 'dialogue_review' || item.type === 'open_text'));
  const limit = closingIndex === -1 ? state.queue.length : closingIndex;
  const position = Math.min(limit, state.current + 5);
  state.queue.splice(position, 0, clone);
  state.itemStatus.splice(position, 0, 'retry');
  return true;
}

// ---------------------------------------------------------------------------
// Sessões interrompíveis: salvar a cada pergunta, retomar, mapa de perguntas
// ---------------------------------------------------------------------------

const STATUS_LABELS = {
  new: 'ainda não respondida', correct: 'acertou', partial: 'acertou em parte', wrong: 'errou',
  pending: 'produção salva (aguarda correção)', seen: 'vista', retry: 'volta para recuperar',
};
const STATUS_GLYPHS = { correct: '✓', partial: '◐', wrong: '✕', pending: '…', seen: '·', retry: '↻', new: '' };
const MODE_TITLES = {
  study: 'Treino misto', diagnostic: 'Diagnóstico', review: 'Revisão espaçada', difficult: 'Itens difíceis',
  flashcards: 'Flashcards', writing: 'Produção escrita',
};

function timeAgo(isoText) {
  const seconds = Math.max(0, (Date.now() - new Date(isoText).getTime()) / 1000);
  if (seconds < 90) return 'agora há pouco';
  if (seconds < 3600) return `há ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `há ${Math.round(seconds / 3600)} h`;
  const days = Math.round(seconds / 86400);
  return days === 1 ? 'ontem' : `há ${days} dias`;
}

function sessionLabel(session) {
  const at = Math.min(session.resume_index + 1, session.total);
  return `pergunta ${at} de ${session.total} · ${session.answered} ${session.answered === 1 ? 'resposta' : 'respostas'} · ${timeAgo(session.updated_at)}`;
}

function sessionKeyForStudy(mode, unitId) {
  return `study:${state.courseId}:${unitId || 'all'}:${mode}`;
}

function activeSession(key) {
  return (state.activeSessions || []).find(session => session.key === key);
}

function beginTracking({ key, kind, title, meta = {} }) {
  state.sessionKey = key;
  state.sessionKind = kind;
  state.sessionTitle = title;
  state.sessionMeta = meta;
  state.itemStatus = state.queue.map(() => 'new');
  if (kind !== 'vocab') { state.vocabRetries = {}; state.vocabPart = ''; }
  state.answeredCurrent = false;
  state.sessionElapsed = 0;
  state.sessionClock = performance.now();
}

function compactQueue() {
  return state.queue.map(ex => {
    const item = { id: ex.id };
    if (Array.isArray(ex.options) && ex.options.length) item.options = ex.options;
    if (ex.retry) item.retry = true;
    if (ex.unit_id === 'lexical_minimum_morphology' && ex.type === 'input') item.fmt = 'input';
    return item;
  });
}

function compactResults() {
  return state.results.map(item => ({
    exercise_id: item.exercise_id, is_correct: item.is_correct, is_partial: Boolean(item.is_partial),
    score: item.score, retry: Boolean(item.retry), prompt: item.prompt || '', correct_answer: item.correct_answer || '',
  }));
}

function resumeIndex() {
  return Math.min(state.queue.length, state.current + (state.answeredCurrent ? 1 : 0));
}

function setSaveState(text, failed = false) {
  const element = $('#saveState');
  if (!element) return;
  element.textContent = text;
  element.classList.toggle('failed', failed);
}

// As gravações são encadeadas: uma resposta antiga nunca sobrescreve uma nova.
function persistSession({ keepalive = false } = {}) {
  if (!state.sessionKey || !state.queue.length) return Promise.resolve();
  const now = performance.now();
  state.sessionElapsed += Math.min(now - state.sessionClock, 300000);
  state.sessionClock = now;
  const body = JSON.stringify({
    key: state.sessionKey,
    kind: state.sessionKind,
    course_id: state.courseId,
    title: state.sessionTitle,
    resume_index: resumeIndex(),
    answered: state.results.filter(item => !item.retry).length,
    elapsed_ms: Math.round(state.sessionElapsed),
    queue: compactQueue(),
    status: state.itemStatus,
    results: compactResults(),
    meta: { ...state.sessionMeta, sessionMode: state.sessionMode, vocabPart: state.vocabPart || '', retries: state.vocabRetries || {} },
  });
  setSaveState('salvando…');
  state.saveChain = state.saveChain.then(() => fetch('/api/session/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: keepalive && body.length < 60000,
  }).then(response => {
    setSaveState(response.ok ? '✓ progresso salvo' : '⚠ não foi possível salvar', !response.ok);
  }).catch(() => setSaveState('⚠ não foi possível salvar', true)));
  return state.saveChain;
}

async function completeTracking() {
  const key = state.sessionKey;
  state.sessionKey = null;
  if (!key) return;
  await state.saveChain;
  try {
    await api('/api/session/complete', { method: 'POST', body: JSON.stringify({ key }) });
  } catch (_) { /* a sessão concluída só deixa de ser oferecida para retomar */ }
  loadActiveSessions();
}

async function discardSavedSession(key) {
  try {
    await api('/api/session/discard', { method: 'POST', body: JSON.stringify({ key }) });
  } catch (_) { /* nada a descartar */ }
}

function exitSession() {
  const key = state.sessionKey;
  const hadProgress = state.results.length > 0 || resumeIndex() > 0;
  stopAllAudio();
  const finish = () => {
    state.sessionKey = null;
    quitSession();
    loadActiveSessions();
  };
  if (!key) { finish(); return; }
  if (hadProgress) {
    persistSession().then(() => {
      showToast(state.sessionKind === 'lesson'
        ? 'Progresso salvo. Ao abrir a aula de novo, ela continua de onde você parou.'
        : 'Progresso salvo. Continue depois em Praticar → Continuar de onde parou.');
      finish();
    });
  } else {
    discardSavedSession(key).then(finish);
  }
}

function updateItemStatus(result) {
  state.itemStatus[state.current] = result.is_correct == null ? 'pending'
    : result.is_correct ? 'correct' : result.is_partial ? 'partial' : 'wrong';
  state.answeredCurrent = true;
}

async function loadActiveSessions() {
  try {
    const data = await api(`/api/session/active?course_id=${encodeURIComponent(state.courseId)}`);
    state.activeSessions = data.sessions || [];
  } catch (_) {
    state.activeSessions = [];
  }
  renderResumePanel();
  if (state.bootstrap) renderLessons();
  if (state.vocabData && $('#vocabView')?.classList.contains('active')) renderVocabModule();
  if (state.vocabLesson?.id && $('#vocabView')?.classList.contains('active') && !state.queue.length) markVocabParts();
}

function renderResumePanel() {
  const panel = $('#resumePanel');
  if (!panel) return;
  // Aulas em andamento aparecem na lista de Aulas; aqui ficam só os treinos. Sessões do antigo
  // "Estudar por unidade" (study:<curso>:<unidade>:<modo>) foram substituídas pela aula e ficam de fora.
  const sessions = (state.activeSessions || []).filter(session =>
    session.kind !== 'lesson' && !(session.kind === 'study' && !session.key.includes(':all:')));
  panel.classList.toggle('hidden', sessions.length === 0);
  $('#resumeList').innerHTML = sessions.map(session => {
    const percent = session.total ? Math.round(100 * Math.min(session.resume_index, session.total) / session.total) : 0;
    return `<div class="resume-item">
      <div class="resume-info">
        <b>${escapeHtml(session.title)}</b>
        <span>${escapeHtml(sessionLabel(session))}</span>
        <span class="vocab-bar"><i style="width:${percent}%"></i></span>
      </div>
      <div class="resume-buttons">
        <button type="button" class="primary" data-resume="${escapeHtml(session.key)}">Continuar</button>
        <button type="button" class="ghost-button" data-discard="${escapeHtml(session.key)}" title="Descartar a posição salva (o histórico de respostas fica)">Descartar</button>
      </div>
    </div>`;
  }).join('');
  $$('#resumeList [data-resume]').forEach(button => button.addEventListener('click', () => resumeSession(button.dataset.resume)));
  $$('#resumeList [data-discard]').forEach(button => button.addEventListener('click', async () => {
    const session = activeSession(button.dataset.discard);
    if (!window.confirm(`Descartar a posição salva em «${session?.title || 'esta sessão'}»? As respostas já dadas continuam no histórico.`)) return;
    await discardSavedSession(button.dataset.discard);
    loadActiveSessions();
  }));
}

function askResume(saved) {
  return new Promise(resolve => {
    const dialog = $('#resumeDialog');
    $('#resumeDialogTitle').textContent = saved.title;
    $('#resumeDialogInfo').textContent = `Você parou na ${sessionLabel(saved)}.`;
    $('#resumeDialogBar i').style.width = `${saved.total ? Math.round(100 * Math.min(saved.resume_index, saved.total) / saved.total) : 0}%`;
    let settled = false;
    const settle = value => {
      if (settled) return;
      settled = true;
      dialog.close();
      resolve(value);
    };
    $('#resumeContinue').onclick = () => settle('resume');
    $('#resumeRestart').onclick = () => settle('restart');
    $('#resumeCancel').onclick = () => settle('cancel');
    dialog.addEventListener('close', () => settle('cancel'), { once: true });
    dialog.showModal();
    $('#resumeContinue').focus();
  });
}

// 'new' = seguir com uma sessão nova; 'resumed' = já retomada; 'cancel' = desistiu.
async function resolveResume(key, { jumpId = null } = {}) {
  let saved = null;
  try {
    const data = await api(`/api/session/active?course_id=${encodeURIComponent(state.courseId)}`);
    state.activeSessions = data.sessions || [];
    saved = activeSession(key);
  } catch (_) { /* sem rede de dados: começa do zero */ }
  if (!saved) return 'new';
  if (jumpId) return (await resumeSession(key, { jumpId })) ? 'resumed' : 'new';
  const choice = await askResume(saved);
  if (choice === 'cancel') return 'cancel';
  if (choice === 'resume') return (await resumeSession(key)) ? 'resumed' : 'new';
  return 'new';
}

const SESSION_HOSTS = {
  lesson: { host: '#lessonArea', view: 'lesson', content: null },
  study: { host: '#sessionArea', view: 'study', content: null },
  vocab: { host: '#vocabGameArea', view: 'vocab', content: '#vocabContent' },
  prefix: { host: '#prefixGameArea', view: 'prefixes', content: '#prefixesContent' },
  morph: { host: '#morphologyGameArea', view: 'morphology', content: '#morphologyContent' },
};

function mountSessionHost(kind) {
  const config = SESSION_HOSTS[kind] || SESSION_HOSTS.study;
  setView(config.view);
  if (config.content) $(config.content).classList.add('hidden');
  $(config.host).classList.remove('hidden');
  state.sessionHost = config.host;
}

async function resumeSession(key, { jumpId = null } = {}) {
  let data;
  try {
    data = await api(`/api/session/get?key=${encodeURIComponent(key)}`);
  } catch (error) {
    showToast(error.message);
    loadActiveSessions();
    return false;
  }
  const { session, exercises, status, results, meta } = data;
  if (!exercises.length) {
    await discardSavedSession(key);
    showToast('O conteúdo desta sessão mudou e ela não pode ser retomada. Comece de novo.');
    loadActiveSessions();
    return false;
  }
  stopAllAudio();
  state.warmAudioController?.abort();
  state.queue = exercises;
  state.itemStatus = status;
  state.results = results.map(item => ({ ...item }));
  state.sessionKey = key;
  state.sessionKind = session.kind;
  state.sessionTitle = session.title;
  state.sessionMeta = { lessonId: meta.lessonId || '', unitId: meta.unitId || '' };
  state.sessionMode = meta.sessionMode || 'study';
  if (session.kind === 'lesson') {
    const unit = courseUnits().find(item => item.id === meta.unitId);
    if (!unit) {
      await discardSavedSession(key);
      return false;
    }
    state.lesson = { unit, steps: unit.lesson_flow || [], unlocked: true };
  }
  state.vocabRetries = meta.retries || {};
  state.vocabPart = meta.vocabPart || '';
  if (meta.lessonId) state.vocabLesson = { id: meta.lessonId };
  state.sessionElapsed = session.elapsed_ms || 0;
  state.sessionClock = performance.now();
  state.current = Math.min(session.resume_index, exercises.length);
  mountSessionHost(session.kind);
  if (data.dropped) showToast(`${data.dropped} pergunta(s) saíram do conteúdo desde a última vez e foram ignoradas.`);
  if (state.current >= exercises.length) {
    renderSessionComplete();
    return true;
  }
  if (jumpId) {
    const index = exercises.findIndex(item => item.id === jumpId && !item.retry);
    if (index >= 0) state.current = index;
  }
  if (!data.dropped) showToast(`Retomando na ${sessionLabel(session).split(' · ')[0]}.`);
  renderExercise();
  if (session.kind === 'vocab') warmDialogueAudio(exercises.find(item => item.lines)?.lines || []);
  return true;
}

function jumpTo(index) {
  $('#mapDialog').close();
  stopAllAudio();
  state.current = Math.max(0, Math.min(index, state.queue.length - 1));
  renderExercise();
}

function openSessionMap() {
  $('#mapDialogTitle').textContent = state.sessionTitle || 'Esta sessão';
  const counts = {};
  state.itemStatus.forEach(value => { counts[value] = (counts[value] || 0) + 1; });
  $('#mapDialogGrid').innerHTML = state.queue.map((ex, index) => {
    const status = state.itemStatus[index] || 'new';
    const label = `${index + 1}. ${typeLabels[ex.type] || 'Tela'} — ${(ex.prompt || ex.head || ex.front || '').slice(0, 90)} (${STATUS_LABELS[status]})`;
    return `<button type="button" class="map-cell st-${status}${index === state.current ? ' current' : ''}" data-index="${index}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"><span>${index + 1}</span></button>`;
  }).join('');
  $('#mapLegend').innerHTML = ['correct', 'partial', 'wrong', 'pending', 'seen', 'retry', 'new']
    .filter(status => counts[status])
    .map(status => `<span class="map-key"><i class="map-cell st-${status}"></i>${STATUS_LABELS[status]} (${counts[status]})</span>`).join('');
  $$('#mapDialogGrid .map-cell').forEach(button => button.addEventListener('click', () => jumpTo(Number(button.dataset.index))));
  $('#mapDialog').showModal();
  $('#mapDialogGrid .current')?.scrollIntoView({ block: 'center' });
}

// -------------- registro pergunta a pergunta (unidade ou lição) --------------

function questionMapMarkup(data, partNames = {}) {
  const counts = data.counts;
  const summary = [
    counts.correct ? `${counts.correct} acertadas` : '', counts.partial ? `${counts.partial} em parte` : '',
    counts.wrong ? `${counts.wrong} erradas` : '', counts.pending ? `${counts.pending} aguardando correção` : '',
    `${counts.new} por responder`,
  ].filter(Boolean).join(' · ');
  const groups = [];
  data.cells.forEach(cell => {
    let group = groups[groups.length - 1];
    if (!group || group.part !== cell.part) { group = { part: cell.part, cells: [] }; groups.push(group); }
    group.cells.push(cell);
  });
  return `<p class="map-summary">${escapeHtml(summary)}</p>
    ${groups.map(group => `<div class="map-group">
      ${group.part ? `<p class="eyebrow">PARTE ${escapeHtml(group.part)} · ${escapeHtml(partNames[group.part] || '')}</p>` : ''}
      <div class="question-map">${group.cells.map(cell => {
        const label = `${cell.n}. ${typeLabels[cell.type] || 'Tela'} — ${cell.label} (${STATUS_LABELS[cell.state]}${cell.mastered ? ', dominada' : ''}${cell.attempts ? `, ${cell.attempts} tentativa(s)` : ''})`;
        return `<button type="button" class="map-cell st-${cell.state}${cell.mastered ? ' mastered' : ''}" data-id="${escapeHtml(cell.id)}" data-part="${escapeHtml(cell.part)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"><span>${cell.n}</span></button>`;
      }).join('')}</div>
    </div>`).join('')}
    <div class="map-legend">${['correct', 'partial', 'wrong', 'pending', 'new'].map(status => `<span class="map-key"><i class="map-cell st-${status}"></i>${STATUS_LABELS[status]}</span>`).join('')}<span class="map-key"><i class="map-cell st-correct mastered"></i>dominada</span></div>
    <p class="muted map-hint">Toque numa pergunta para abrir a sessão direto nela. A cor mostra o último resultado.</p>`;
}

async function loadQuestionMap(host, scope, partNames, onPick) {
  host.innerHTML = '<p class="muted">Carregando o registro…</p>';
  try {
    const data = await api(`/api/progress/map?scope=${encodeURIComponent(scope)}`);
    host.innerHTML = questionMapMarkup(data, partNames);
    $$('.map-cell[data-id]', host).forEach(button => button.addEventListener('click', () => onPick({ id: button.dataset.id, part: button.dataset.part })));
  } catch (error) {
    host.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

function markVocabParts() {
  const detail = $('#vocabLessonDetail');
  const lessonId = detail?.querySelector('.vocab-detail')?.dataset.lesson;
  if (!lessonId) return;
  $$('.vocab-part', detail).forEach(button => {
    const saved = activeSession(`vocab:${lessonId}:${button.dataset.part}`);
    let note = button.querySelector('.part-session');
    if (!saved) { note?.remove(); button.classList.remove('in-progress'); return; }
    if (!note) { note = document.createElement('em'); note.className = 'part-session'; button.appendChild(note); }
    button.classList.add('in-progress');
    note.textContent = `▶ em andamento: ${Math.min(saved.resume_index + 1, saved.total)}/${saved.total}`;
  });
}

function renderDashboard() {
  const s = state.summary;
  const due = s.due_count || 0;
  $('#dueBadge').textContent = due;
  $('#dueBadge').classList.toggle('hidden', !due);
  const units = trailUnits();
  const progress = unitProgressMap();
  const done = units.filter(unit => progress[unit.id]?.completed).length;
  $('#metrics').innerHTML = [
    ['Aulas concluídas', `${done}/${units.length}`, done === units.length ? 'programa completo' : `próxima: aula ${done + 1}`],
    ['Precisão geral', s.accuracy == null ? '—' : `${s.accuracy}%`, `${s.correct} exatas · ${s.partial || 0} parciais`],
    ['Revisões de hoje', due, 'itens vencidos agora'],
    ['Consolidados', s.mature_count, `de ${s.tracked_cards} itens praticados`],
  ].map(([label, value, note]) => `
    <article class="metric"><span>${label}</span><strong>${value}</strong><em>${note}</em></article>
  `).join('');

  const mastery = s.by_tag.filter(item => item.attempts >= 1).slice(0, 12);
  $('#masteryList').innerHTML = mastery.length ? mastery.map(item => {
    const level = item.mastery < 55 ? 'low' : item.mastery < 78 ? 'mid' : '';
    return `<div class="mastery-row">
      <span title="${escapeHtml(item.tag)}">${escapeHtml(item.tag)}</span>
      <div class="bar"><i class="${level}" style="width:${item.mastery}%"></i></div>
      <b>${item.mastery}%</b>
    </div>`;
  }).join('') : '<div class="empty-state">Faça a primeira aula para formar seu mapa de domínio.</div>';

  if (state.bootstrap) renderLessons();
  if ($('#practiceView').classList.contains('active')) renderPractice();
}

function unitProgressMap() {
  const list = (state.summary && state.summary.unit_progress) || [];
  const map = {};
  list.forEach(item => { map[item.unit_id] = item; });
  return map;
}

// Unidades com order 0 (diagnóstico) ficam fora da contagem "1, 2, 3…" da trilha,
// para não deslocar o número de todas as unidades seguintes.
function unitDisplayNumbers(units) {
  const map = {};
  let n = 0;
  units.forEach(unit => {
    if (unit.order === 0) return;
    n += 1;
    map[unit.id] = n;
  });
  return map;
}

// ------------------------------- Aulas ---------------------------------
// Cada unidade da trilha é uma aula de modelo único: abertura → explicação →
// tabela → exercícios na ordem do roteiro (lesson_flow) → conclusão.

const LESSON_SCREENS = new Set(['lesson_intro', 'lesson_explain', 'lesson_table']);

function trailUnits() {
  return courseUnits().filter(unit => unit.order > 0);
}

function lessonNumber(unit) {
  return unitDisplayNumbers(courseUnits())[unit.id];
}

function lessonHeading(unit) {
  const number = lessonNumber(unit);
  return number ? `Aula ${number} · ${unit.title}` : unit.title;
}

function lessonSessionKey(unitId, suffix = '') {
  return `lesson:russian:${unitId}${suffix}`;
}

function lessonStatus(unit) {
  const p = unitProgressMap()[unit.id] || { unlocked: true, completed: false, cleared: 0, total: 0, percent: 0 };
  const saved = activeSession(lessonSessionKey(unit.id)) || activeSession(lessonSessionKey(unit.id, ':reforco'));
  if (p.completed) return { ...p, saved, kind: 'done', label: 'Concluída' };
  if (!p.unlocked) return { ...p, saved, kind: 'locked', label: 'Bloqueada' };
  if (saved) return { ...p, saved, kind: 'progress', label: `Em andamento · ${Math.min(saved.resume_index + 1, saved.total)}/${saved.total}` };
  if (p.cleared) return { ...p, saved, kind: 'progress', label: `${p.cleared}/${p.total} dominados` };
  return { ...p, saved, kind: 'open', label: 'Disponível' };
}

function renderLessons() {
  const units = trailUnits();
  if (!units.length) return;
  const statuses = Object.fromEntries(units.map(unit => [unit.id, lessonStatus(unit)]));
  const done = units.filter(unit => statuses[unit.id].kind === 'done').length;
  const current = units.find(unit => statuses[unit.id].kind !== 'done');
  $('#lessonCount').textContent = `${done} de ${units.length} concluídas`;

  if (current) {
    const status = statuses[current.id];
    const action = status.saved ? 'Continuar a aula' : 'Começar a aula';
    $('#currentLesson').innerHTML = `<div>
        <span class="hero-kicker">AULA ${lessonNumber(current)} DE ${units.length} · ${status.saved ? 'EM ANDAMENTO' : 'PRÓXIMA AULA'}</span>
        <h2>${escapeHtml(current.title)}</h2>
        <p>${escapeHtml(current.description || '')}</p>
        ${(current.objectives || []).length ? `<ul class="hero-objectives">${current.objectives.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
        <div class="hero-actions">
          <button class="primary" data-open-lesson="${escapeHtml(current.id)}">${action}</button>
          ${status.total ? `<span class="hero-progress">${status.cleared}/${status.total} exercícios dominados · ${current.estimated_minutes || 25} min</span>` : ''}
        </div>
      </div>
      <div class="hero-number" aria-hidden="true">${lessonNumber(current)}</div>`;
  } else {
    $('#currentLesson').innerHTML = `<div>
        <span class="hero-kicker">ПРОГРАММА ЗАВЕРШЕНА</span>
        <h2>Você concluiu as ${units.length} aulas.</h2>
        <p>Continue firme com a revisão espaçada e os treinos de Praticar. Qualquer aula pode ser refeita pela lista abaixo.</p>
        <div class="hero-actions"><button class="primary" data-go-practice>Ir para Praticar</button></div>
      </div><div class="hero-number" aria-hidden="true">✓</div>`;
  }

  $('#lessonList').innerHTML = units.map(unit => {
    const status = statuses[unit.id];
    return `<li><button type="button" class="lesson-row ${status.kind}${current && unit.id === current.id ? ' current' : ''}" data-open-lesson="${escapeHtml(unit.id)}">
      <span class="lesson-num">${status.kind === 'done' ? '✓' : lessonNumber(unit)}</span>
      <span class="lesson-text"><b>${escapeHtml(unit.title)}</b><small>${escapeHtml(unit.description || '')}</small></span>
      <span class="lesson-state">${status.kind === 'locked' ? '🔒 ' : ''}${escapeHtml(status.label)}
        ${status.total && status.kind !== 'locked' ? `<span class="vocab-bar"><i style="width:${status.percent}%"></i></span>` : ''}</span>
    </button></li>`;
  }).join('');
  $$('[data-open-lesson]').forEach(button => button.addEventListener('click', () => openLesson(button.dataset.openLesson)));
  $('[data-go-practice]')?.addEventListener('click', () => setView('practice'));
}

async function openLesson(unitId, { restart = false } = {}) {
  const unit = courseUnits().find(item => item.id === unitId);
  if (!unit) return;
  stopAllAudio();
  const key = lessonSessionKey(unitId);
  state.lesson = { unit, steps: unit.lesson_flow || [], unlocked: true };
  if (!restart) {
    try {
      state.activeSessions = (await api(`/api/session/active?course_id=russian`)).sessions || [];
    } catch (_) { /* sem sessões salvas: começa do zero */ }
    const reinforcement = lessonSessionKey(unitId, ':reforco');
    if (activeSession(key) && await resumeSession(key)) return;
    if (activeSession(reinforcement) && await resumeSession(reinforcement)) return;
  } else {
    await discardSavedSession(key);
  }
  let data;
  try {
    data = await api(`/api/lesson?unit_id=${encodeURIComponent(unitId)}`);
  } catch (error) {
    showToast(error.message);
    return;
  }
  state.lesson = { unit: data.unit, steps: data.steps || [], unlocked: data.unlocked };
  startLessonQueue(data.items, data.unlocked ? key : null, lessonHeading(unit));
}

function startLessonQueue(items, key, title) {
  state.queue = items;
  state.current = 0;
  state.results = [];
  state.sessionMode = 'lesson';
  state.sessionHost = '#lessonArea';
  // Aula bloqueada (só leitura) não gera sessão salva.
  beginTracking({ key, kind: 'lesson', title, meta: { unitId: state.lesson.unit.id } });
  setView('lesson');
  renderExercise();
}

async function startLessonReinforcement(unitId) {
  const unit = courseUnits().find(item => item.id === unitId);
  let data;
  let map;
  try {
    [data, map] = await Promise.all([
      api(`/api/lesson?unit_id=${encodeURIComponent(unitId)}`),
      api(`/api/progress/map?scope=${encodeURIComponent(`unit:${unitId}`)}`),
    ]);
  } catch (error) {
    showToast(error.message);
    return;
  }
  const missing = new Set(map.cells.filter(cell => !cell.mastered).map(cell => cell.id));
  const items = data.items.filter(item => missing.has(item.id));
  if (!items.length) { showToast('Nada a reforçar: todos os exercícios estão dominados.'); return; }
  state.lesson = { unit: data.unit, steps: data.steps || [], unlocked: true };
  startLessonQueue(items, lessonSessionKey(unitId, ':reforco'), `${lessonHeading(unit)} · reforço`);
}

function lessonStepInfo(ex) {
  const steps = state.lesson?.steps || [];
  if (state.sessionMode !== 'lesson' || ex.step == null || !steps.length) return null;
  const index = Math.min(ex.step, steps.length - 1);
  const previous = state.queue[state.current - 1];
  return {
    label: `PARTE ${index + 1} DE ${steps.length} · ${String(steps[index].title || '').toUpperCase()}`,
    title: `Parte ${index + 1} · ${steps[index].title || ''}`,
    description: steps[index].description || '',
    starts: !previous || previous.step !== ex.step,
  };
}

function sessionTopMarkup() {
  const percentage = Math.round(100 * state.current / state.queue.length);
  const lessonMode = state.sessionMode === 'lesson';
  return `<div class="session-top">
      <button class="quit-session" title="Sair e guardar onde você parou">← Sair</button>
      <div class="session-progress"><i style="width:${percentage}%"></i></div>
      <span class="session-counter">${state.current + 1} / ${state.queue.length}</span>
      ${state.sessionKey && !lessonMode ? '<button type="button" class="map-session" title="Mapa das perguntas: ver o que já respondeu e pular para qualquer uma">▦ Mapa</button>' : ''}
      ${state.sessionKey ? '<span id="saveState" class="save-state" role="status"></span>' : ''}
    </div>`;
}

function lessonTablesMarkup(tables) {
  return tables.map(table => `<div class="memory-table-block">
      <h4>${escapeHtml(table.title || 'Tabela de memorização')}</h4>
      <div class="table-scroll"><table class="ending-table memory-table">
        <thead><tr>${(table.columns || []).map(col => `<th>${escapeHtml(col)}</th>`).join('')}</tr></thead>
        <tbody>${(table.rows || []).map(row => `<tr>${row.map(cell => `<td>${interactiveRussianText(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table></div>
      ${table.note ? `<p class="memory-note">${escapeHtml(table.note)}</p>` : ''}
    </div>`).join('');
}

function renderLessonScreen(ex) {
  const { unit, steps, unlocked } = state.lesson;
  const next = state.queue[state.current + 1];
  const previous = state.queue[state.current - 1];
  let body = '';
  let action = 'Continuar';
  if (ex.type === 'lesson_intro') {
    const objectives = unit.objectives || [];
    body = `<p class="eyebrow">AULA ${lessonNumber(unit) || ''} · ABERTURA</p>
      <h2 class="lesson-title">${escapeHtml(unit.title)}</h2>
      <p class="lesson-lead">${escapeHtml(unit.description || '')}</p>
      ${objectives.length ? `<h3 class="lesson-subtitle">Ao final desta aula você vai</h3><ul class="lesson-objectives">${objectives.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
      <h3 class="lesson-subtitle">O caminho da aula</h3>
      <ol class="lesson-path">
        <li><b>Explicação</b><span>A gramática da aula, com exemplos para ouvir.</span></li>
        ${steps.map(step => `<li><b>${escapeHtml(step.title || '')}</b><span>${escapeHtml(step.description || '')}</span></li>`).join('')}
      </ol>
      ${unlocked ? '' : '<p class="lesson-locked-note">🔒 Os exercícios desta aula abrem quando você concluir a aula anterior. A explicação você já pode ler e ouvir.</p>'}`;
    action = 'Começar a aula';
  } else if (ex.type === 'lesson_explain') {
    body = `<p class="eyebrow">EXPLICAÇÃO · ${ex.block_index + 1} DE ${ex.block_total}</p>
      ${renderGrammarBlock(unit.id, ex.block, ex.block_index)}`;
  } else if (ex.type === 'lesson_table') {
    body = `<p class="eyebrow">PARA GUARDAR</p>
      <p class="lesson-lead">Antes dos exercícios, releia a tabela. Ela resume o que você vai usar a seguir.</p>
      ${lessonTablesMarkup(ex.tables || [])}`;
  }
  if (!next) action = unlocked ? 'Concluir' : 'Terminar a leitura';
  else if (!LESSON_SCREENS.has(next.type)) action = 'Começar os exercícios';
  $(state.sessionHost).innerHTML = `${sessionTopMarkup()}
    <article class="exercise-card lesson-screen">
      ${body}
      <div class="continue-row lesson-nav">
        ${previous && LESSON_SCREENS.has(previous.type) ? '<button type="button" class="secondary lesson-back">← Voltar</button>' : ''}
        <button type="button" class="primary continue-ungraded">${escapeHtml(action)}</button>
      </div>
    </article>`;
  const host = $(state.sessionHost);
  $('.quit-session', host).addEventListener('click', exitSession);
  $('.lesson-back', host)?.addEventListener('click', () => { stopAllAudio(); state.current -= 1; renderExercise(); });
  $('.continue-ungraded', host).addEventListener('click', () => { stopAllAudio(); nextExercise(); });
  $$('.example-speak', host).forEach(button => button.addEventListener('click', () => speakText(button.dataset.text, button)));
  bindInteractiveWords();
  bindLessonAudio(host);
  bindResponseEvents(ex);
  persistSession();
}

async function renderLessonComplete() {
  completeTracking();
  const { unit, unlocked } = state.lesson;
  const host = $(state.sessionHost);
  const backButton = '<button class="secondary lesson-home">Voltar às aulas</button>';
  if (!unlocked) {
    host.innerHTML = `<article class="panel session-complete">
      <p class="eyebrow">LEITURA CONCLUÍDA</p>
      <h2>${escapeHtml(lessonHeading(unit))}</h2>
      <p>Os exercícios desta aula abrem quando você concluir a aula anterior.</p>
      <div class="hero-actions" style="justify-content:center">${backButton}</div>
    </article>`;
    $('.lesson-home', host).addEventListener('click', () => { quitSession(); });
    return;
  }
  try {
    state.summary = await api('/api/summary?course_id=russian');
    renderDashboard();
  } catch (_) { /* mostra com o resumo que já tinha */ }
  const p = unitProgressMap()[unit.id] || { cleared: 0, total: 0, completed: false };
  const graded = state.results.filter(item => item.is_correct != null);
  const points = graded.reduce((sum, item) => sum + Number(item.score || 0), 0);
  const score = graded.length ? Math.round(100 * points / graded.length) : 0;
  const units = trailUnits();
  const nextUnit = units[units.findIndex(item => item.id === unit.id) + 1];
  const vocabLesson = (state.vocabData?.lessons || []).find(lesson => lesson.unit_id === unit.id);
  const missed = [...new Map(state.results.filter(item => item.is_correct === false).map(item => [item.exercise_id, item])).values()];
  const missedHtml = missed.length ? `<div class="vocab-missed"><p class="eyebrow">PARA REVER</p><ul>${missed.map(item => `<li><span>${interactiveRussianText(item.prompt)}</span><b>${escapeHtml(item.correct_answer || '')}</b></li>`).join('')}</ul></div>` : '';
  if (p.completed) {
    host.innerHTML = `<article class="panel session-complete">
      <p class="eyebrow">AULA CONCLUÍDA</p>
      <div class="result-ring" style="--score:${score}%"><b>${graded.length ? `${score}%` : '✓'}</b></div>
      <h2>${escapeHtml(lessonHeading(unit))}</h2>
      <p>Você domina ${p.cleared} de ${p.total} exercícios. ${nextUnit ? `A aula ${lessonNumber(nextUnit)} está liberada.` : 'Essa era a última aula do programa.'}</p>
      ${missedHtml}
      <div class="hero-actions" style="justify-content:center">
        ${nextUnit ? `<button class="primary lesson-next">Próxima aula: ${escapeHtml(nextUnit.title)}</button>` : ''}
        ${vocabLesson ? '<button class="secondary lesson-vocab">Praticar o vocabulário desta aula</button>' : ''}
        ${backButton}
      </div>
    </article>`;
  } else {
    const needed = Math.max(1, Math.ceil(0.75 * p.total) - p.cleared);
    host.innerHTML = `<article class="panel session-complete">
      <p class="eyebrow">QUASE LÁ</p>
      <div class="result-ring" style="--score:${p.percent || 0}%"><b>${p.cleared}/${p.total}</b></div>
      <h2>Falta pouco para concluir a aula</h2>
      <p>Para liberar a próxima aula, domine pelo menos 75% dos exercícios. Você domina ${p.cleared} de ${p.total}; faltam ${needed}.</p>
      ${missedHtml}
      <div class="hero-actions" style="justify-content:center">
        <button class="primary lesson-reinforce">Refazer os exercícios que faltam</button>
        ${backButton}
      </div>
    </article>`;
  }
  bindInteractiveWords();
  $('.lesson-home', host).addEventListener('click', () => quitSession());
  $('.lesson-next', host)?.addEventListener('click', () => openLesson(nextUnit.id));
  $('.lesson-vocab', host)?.addEventListener('click', () => { quitSession({ silent: true }); goToVocabLesson(vocabLesson.id); });
  $('.lesson-reinforce', host)?.addEventListener('click', () => startLessonReinforcement(unit.id));
}

// ------------------------------ Praticar --------------------------------

function renderPractice() {
  if (!state.summary) return;
  const due = state.summary.due_count || 0;
  const cards = [
    { id: 'review', mark: '↻', title: 'Revisão espaçada', text: due ? `${due} ${due === 1 ? 'item vencido' : 'itens vencidos'} das aulas que você já fez. Um erro volta logo; um acerto volta cada vez mais tarde.` : 'Nada vencido agora. As respostas das aulas alimentam esta fila sozinhas.', action: due ? 'Revisar agora' : 'Sem revisões hoje', disabled: !due },
    { id: 'difficult', mark: '△', title: 'Itens difíceis', text: 'Os exercícios em que você mais errou, todos juntos.', action: 'Treinar' },
    { id: 'vocab', mark: 'Л', title: 'Vocabulário em diálogo', text: 'Uma cena com vozes por aula: ouvir, recuperar e usar as construções da aula.', action: 'Abrir' },
    { id: 'morphology', mark: 'Ы', title: 'Terminações e léxico', text: 'Tabelas de casos e um jogo com palavras reais do léxico mínimo TRKI-II.', action: 'Abrir' },
    { id: 'prefixes', mark: 'П', title: 'Verbos com prefixo', text: 'Prefixo por prefixo, e contrastes entre eles.', action: 'Abrir' },
    { id: 'errors', mark: '✕', title: 'Caderno de erros', text: 'Seus erros mais recentes com a forma esperada ao lado.', action: 'Ver' },
    { id: 'diagnostic', mark: '◆', title: 'Diagnóstico geral', text: 'Um teste sem pistas que mistura o conteúdo de todo o programa.', action: 'Fazer o teste' },
  ];
  $('#practiceGrid').innerHTML = cards.map(card => `<button type="button" class="practice-card" data-practice="${card.id}"${card.disabled ? ' disabled' : ''}>
      <span class="practice-mark">${card.mark}</span>
      <b>${escapeHtml(card.title)}</b>
      <span>${escapeHtml(card.text)}</span>
      <em>${escapeHtml(card.action)} →</em>
    </button>`).join('');
  $$('#practiceGrid [data-practice]').forEach(button => button.addEventListener('click', () => {
    const target = button.dataset.practice;
    if (target === 'review') startSession('review', '');
    else if (target === 'difficult') startSession('difficult', '');
    else if (target === 'diagnostic') startSession('diagnostic', '');
    else setView(target);
  }));
  renderResumePanel();
}

function lessonAudioPlayer(unitId, block, label) {
  const target = block === 'all' ? 'all' : String(block);
  return `<div class="lesson-audio" data-unit="${escapeHtml(unitId)}" data-block="${escapeHtml(target)}">
      <button type="button" class="lesson-audio-play">🔊 ${escapeHtml(label)}</button>
      <span class="lesson-audio-status"></span>
      <audio class="lesson-audio-el" controls preload="none" hidden></audio>
    </div>`;
}

function bindLessonAudio(root = document) {
  $$('.lesson-audio', root).forEach(box => {
    const button = $('.lesson-audio-play', box);
    const audio = $('.lesson-audio-el', box);
    const status = $('.lesson-audio-status', box);
    if (!button || button.dataset.bound === '1') return;
    button.dataset.bound = '1';
    button.addEventListener('click', () => {
      if (!audio.src) {
        const whole = box.dataset.block === 'all';
        const startedAt = Date.now();
        const tick = () => {
          const seconds = Math.round((Date.now() - startedAt) / 1000);
          status.textContent = `Gerando a narração no edge-tts… ${seconds}s (só na primeira vez; depois toca offline)`;
        };
        tick();
        const timer = setInterval(tick, 1000);
        const stop = () => { clearInterval(timer); box.classList.remove('loading'); };
        box.classList.add('loading');
        if (whole) showToast('A aula inteira leva cerca de um minuto para ser gerada na primeira vez.');
        audio.src = `/api/lesson-audio?unit_id=${encodeURIComponent(box.dataset.unit)}&block=${encodeURIComponent(box.dataset.block)}`;
        audio.hidden = false;
        audio.addEventListener('canplay', () => {
          stop();
          status.textContent = '';
        }, { once: true });
        audio.addEventListener('error', () => {
          stop();
          status.textContent = 'Não foi possível gerar o áudio. O edge-tts precisa de internet na primeira vez.';
        }, { once: true });
      }
      $('#ttsPlayer').pause();
      $$('.lesson-audio-el').forEach(other => { if (other !== audio) other.pause(); });
      if (audio.paused) {
        const promise = audio.play();
        if (promise) promise.catch(() => {});
        button.textContent = '⏸ Pausar';
      } else {
        audio.pause();
        button.textContent = '🔊 Retomar';
      }
    });
    audio.addEventListener('ended', () => { button.textContent = '🔊 Ouvir de novo'; });
    audio.addEventListener('pause', () => {
      if (!audio.ended && audio.currentTime > 0) button.textContent = '🔊 Retomar';
    });
  });
}

function renderGrammarBlock(unitId, block, index) {
  const examples = Array.isArray(block.examples) && block.examples.length
    ? `<ul class="grammar-examples">${block.examples.map(example => `<li>
          <button type="button" class="example-speak" data-text="${escapeHtml(example.ru || '')}" title="Ouvir em russo">🔊</button>
          <span class="example-ru">${interactiveRussianText(example.ru || '')}</span>
          <span class="example-pt">${escapeHtml(example.pt || '')}</span>
          ${example.note ? `<span class="example-note">${escapeHtml(example.note)}</span>` : ''}
        </li>`).join('')}</ul>`
    : '';
  const pitfalls = Array.isArray(block.pitfalls) && block.pitfalls.length
    ? `<div class="grammar-pitfalls"><strong>Erro típico de quem fala português</strong><ul>${
        block.pitfalls.map(item => `<li>${interactiveRussianText(item)}</li>`).join('')
      }</ul></div>`
    : '';
  return `<div class="grammar-block">
      <div class="grammar-block-head">
        <h4>${escapeHtml(block.title || '')}</h4>
        ${lessonAudioPlayer(unitId, index, 'Ouvir esta parte')}
      </div>
      ${(block.paragraphs || []).map(paragraph => `<p>${interactiveRussianText(paragraph)}</p>`).join('')}
      ${examples}
      ${pitfalls}
    </div>`;
}

function renderReference() {
  const references = [];
  const seen = new Set();
  courseUnits().forEach(unit => (unit.reference || []).forEach(item => {
    const key = `${item.construction}|${item.question}`;
    if (!seen.has(key)) { seen.add(key); references.push(item); }
  }));
  $('#referenceGrid').innerHTML = references.length ? references.map(item => `<article class="reference-card">
    <h3>${escapeHtml(item.construction)}</h3>
    <div class="question">${escapeHtml(item.question)}</div>
    <span class="case">${escapeHtml(item.case)}</span>
    <p>${escapeHtml(item.meaning || '')}</p>
    ${item.example ? `<blockquote>${escapeHtml(item.example)}</blockquote>` : ''}
  </article>`).join('') : '<div class="empty-state">Ainda não há expressões de referência neste curso.</div>';
}

function renderErrors() {
  const s = state.summary;
  const entries = Object.entries(s.error_types || {});
  $('#errorTypeStats').innerHTML = entries.length ? entries.map(([key, value]) =>
    `<span class="type-chip">${escapeHtml(errorLabels[key] || key)} <b>${value}</b></span>`
  ).join('') : '<span class="muted">Classifique os erros durante os exercícios para gerar este mapa.</span>';

  $('#errorsList').innerHTML = s.recent_errors.length ? s.recent_errors.map(item => `<article class="error-item">
    <time>${new Date(item.created_at).toLocaleString('pt-BR')}</time>
    <h4>${escapeHtml(item.prompt)}</h4>
    <div class="error-answer">
      <div><small>SUA RESPOSTA</small><br>${escapeHtml(item.answer || '—')}</div>
      <div><small>FORMA ESPERADA</small><br>${escapeHtml(item.expected || '—')}</div>
    </div>
    <p class="muted">Crédito ${Math.round(Number(item.score || 0) * 100)}% · ${escapeHtml(errorLabels[item.category] || 'Erro ainda não classificado')}</p>
  </article>`).join('') : '<div class="empty-state">Ainda não há erros registrados.</div>';
}

async function loadPendingWriting() {
  const courseQuery = `course_id=${encodeURIComponent(state.courseId)}`;
  const [data, reports] = await Promise.all([api(`/api/pending-writing?${courseQuery}`), api(`/api/reports?${courseQuery}`)]);
  $('#pendingWriting').innerHTML = data.items.length ? data.items.map(item => `<div class="pending-item">
    <time>${new Date(item.created_at).toLocaleString('pt-BR')} · ${escapeHtml(item.consultation)}</time>
    <b>${escapeHtml(item.exercise_id)}</b>
    <p>${escapeHtml(item.answer_text)}</p>
  </div>`).join('') : '<div class="empty-state">Nenhuma produção enviada ainda.</div>';
  $('#reportedContent').innerHTML = reports.items.length ? reports.items.map(item => `<div class="pending-item">
    <time>${new Date(item.created_at).toLocaleString('pt-BR')}</time>
    <b>${escapeHtml(item.exercise_id)} · ${escapeHtml(item.reason)}</b>
    <p>${escapeHtml(item.prompt_snapshot)}${item.note ? `<br><em>${escapeHtml(item.note)}</em>` : ''}</p>
  </div>`).join('') : '<div class="empty-state">Nenhum problema sinalizado.</div>';
}

async function startSession(mode, unitId = '', opts = {}) {
  const studyKey = sessionKeyForStudy(mode, unitId);
  if (await resolveResume(studyKey, opts) !== 'new') return;
  const params = new URLSearchParams({ mode, course_id: state.courseId });
  if (unitId) params.set('unit_id', unitId);
  let data;
  try {
    data = await api(`/api/exercises?${params}`);
  } catch (error) {
    showToast(error.message);
    return;
  }
  let items = data.exercises;
  // Unidades reformuladas seguem o ciclo recuperar → compreender → praticar → produzir.
  const selectedUnit = unitId && courseUnits().find(unit => unit.id === unitId);
  if (selectedUnit?.lesson_flow && mode === 'study') {
    items = items.map((item, index) => ({ item, index })).sort((a, b) => {
      const rank = exercise => {
        if (state.courseId === 'romanian') {
          if (['reading', 'listening'].includes(exercise.type)) return 1;
          if (exercise.type === 'flashcard' || ['recall', 'retrieval'].includes(exercise.stage)) return 2;
          if (exercise.type === 'open_text' || ['writing_b2', 'micro_writing', 'speaking_plan', 'transfer'].includes(exercise.stage)) return 4;
          return 3;
        }
        if (exercise.type === 'flashcard' || ['recall', 'retrieval', 'spaced_review'].includes(exercise.stage)) return 1;
        if (['reading', 'listening'].includes(exercise.type)) return 2;
        if (exercise.type === 'open_text' || ['writing_b2', 'micro_writing', 'speaking_plan', 'transfer'].includes(exercise.stage)) return 4;
        return 3;
      };
      return rank(a.item) - rank(b.item) || a.index - b.index;
    }).map(entry => entry.item);
  }
  // Sem unidade, o treino mistura itens desbloqueados para prática intercalada.
  const isFixedLesson = Boolean(unitId) || mode === 'diagnostic' || mode === 'review';
  if (!isFixedLesson) items = shuffle(items);
  if (!items.length) {
    showToast(mode === 'review' ? 'Nenhuma revisão vencida agora.' : 'Não há itens nesse filtro ainda.');
    return;
  }
  state.queue = items;
  state.current = 0;
  state.results = [];
  state.sessionMode = mode;
  state.sessionHost = '#sessionArea';
  const unitInfo = unitId ? courseUnits().find(unit => unit.id === unitId) : null;
  const unitNumber = unitInfo ? unitDisplayNumbers(courseUnits())[unitInfo.id] : null;
  beginTracking({
    key: studyKey, kind: 'study',
    title: unitInfo ? `${mode === 'study' ? 'Estudar' : (MODE_TITLES[mode] || 'Estudar')} · ${unitNumber ? `Unidade ${unitNumber} · ` : ''}${unitInfo.title}` : `${MODE_TITLES[mode] || 'Estudar'} · todas as unidades`,
  });
  const studyJump = opts.jumpId ? items.findIndex(item => item.id === opts.jumpId) : -1;
  if (studyJump >= 0) state.current = studyJump;
  setView('study');
  $('#viewTitle').textContent = MODE_TITLES[mode] || 'Praticar';
  $('#sessionArea').classList.remove('hidden');
  renderExercise();
}

function resetExerciseState() {
  state.answeredCurrent = false;
  state.selectedAnswer = '';
  state.builtTokens = [];
  state.matchedPairs = [];
  state.matchSelectedLeft = null;
  state.startedAt = performance.now();
}

function interactiveRussianText(text) {
  return String(text || '').split(/([А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*)/g).map(part => {
    if (/^[А-Яа-яЁё]/.test(part)) {
      return `<button type="button" class="word-button" data-word="${escapeHtml(part)}" title="Ouvir e consultar ${escapeHtml(part)}">${escapeHtml(part)}</button>`;
    }
    return escapeHtml(part);
  }).join('');
}

function ttsUrl(text, voice = '') {
  const params = new URLSearchParams({ text, course_id: state.courseId });
  if (voice) params.set('voice', voice);
  return `/api/tts?${params}`;
}

function stopAllAudio() {
  $('#ttsPlayer').pause();
  $$('.lesson-audio-el').forEach(audio => audio.pause());
  if (state.dialoguePlayer) state.dialoguePlayer.stop();
}

function speakText(text, element = null, playbackRate = 1, voice = '') {
  const hasTargetText = state.courseId === 'romanian'
    ? /[A-Za-zĂÂÎȘŞȚŢăâîșşțţ]/.test(text || '')
    : /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/.test(text || '');
  if (!hasTargetText) return;
  const player = $('#ttsPlayer');
  if (state.speakingElement) state.speakingElement.classList.remove('speaking', 'audio-loading');
  state.speakingElement = element;
  if (element) element.classList.add('speaking', 'audio-loading');
  player.pause();
  if (state.dialoguePlayer) state.dialoguePlayer.stop();
  player.src = ttsUrl(text, voice);
  player.playbackRate = playbackRate;
  const promise = player.play();
  if (promise) promise.catch(() => {
    if (element) element.classList.remove('speaking', 'audio-loading');
    showToast('Não foi possível reproduzir. O edge-tts precisa de internet no primeiro clique.');
  });
  player.onplaying = () => element?.classList.remove('audio-loading');
  player.onended = () => {
    element?.classList.remove('speaking', 'audio-loading');
    if (state.speakingElement === element) state.speakingElement = null;
  };
  player.onerror = () => {
    element?.classList.remove('speaking', 'audio-loading');
    if (state.speakingElement === element) state.speakingElement = null;
  };
}

async function lookupWord(word) {
  const dialog = $('#dictionaryDialog');
  $('#dictionaryContent').innerHTML = `<h2 class="dictionary-word">${escapeHtml(word)}</h2><p class="muted">Consultando forma e lema…</p>`;
  dialog.showModal();
  try {
    const data = await api(`/api/dictionary?word=${encodeURIComponent(word)}`);
    const entries = data.entries.map(entry => `<article class="dictionary-entry">
      <h4>${escapeHtml(entry.accented || entry.lemma)}</h4>
      <p>${escapeHtml(entry.pos)}${entry.gender ? ` · ${escapeHtml(entry.gender)}` : ''}${entry.aspect ? ` · ${escapeHtml(entry.aspect)}` : ''}</p>
      ${entry.translation_pt ? `<p class="translation">${escapeHtml(entry.translation_pt)}</p>` : ''}
      ${entry.translation_en ? `<p><small>INGLÊS</small> ${escapeHtml(entry.translation_en)}</p>` : ''}
      ${entry.grammar ? `<p class="grammar">Nesta forma: ${escapeHtml(entry.grammar)}</p>` : ''}
      ${entry.regency ? `<p class="regency"><b>${escapeHtml(entry.regency)}</b>${entry.case ? `<br>${escapeHtml(entry.case)}` : ''}</p>` : ''}
      ${entry.partner ? `<p><small>PAR ASPECTUAL</small> ${escapeHtml(entry.partner)}</p>` : ''}
    </article>`).join('');
    $('#dictionaryContent').innerHTML = `<h2 class="dictionary-word">${escapeHtml(word)}</h2>
      <p class="dictionary-source-word">Forma pesquisada: ${escapeHtml(data.normalized || word)}</p>
      ${entries || '<p class="empty-state">Forma não encontrada no índice local.</p>'}`;
  } catch (error) {
    $('#dictionaryContent').innerHTML += `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  }
}

function bindInteractiveWords() {
  $$('.word-button').forEach(button => button.addEventListener('click', () => {
    speakText(button.dataset.word, button);
    lookupWord(button.dataset.word);
  }));
}

function openReportDialog(ex) {
  state.reportExercise = ex;
  $('#reportNote').value = '';
  $('#reportReason').value = 'enunciado_confuso';
  $('#reportDialog').showModal();
}

function renderExercise() {
  resetExerciseState();
  const ex = state.queue[state.current];
  if (['vocab_lesson', 'lesson'].includes(state.sessionMode)) window.scrollTo({ top: 0 });
  if (LESSON_SCREENS.has(ex.type)) { renderLessonScreen(ex); return; }
  const step = lessonStepInfo(ex);
  $(state.sessionHost).innerHTML = `
    ${sessionTopMarkup()}
    ${step && step.starts ? `<div class="step-banner"><b>${escapeHtml(step.title)}</b><span>${escapeHtml(step.description)}</span></div>` : ''}
    <article class="exercise-card">
      <div class="exercise-meta">
        <div class="exercise-labels"><span class="exercise-phase">${escapeHtml(step ? step.label : (ex.phase || phaseLabel(ex, state.current)))}</span><span class="exercise-type">${typeLabels[ex.type] || 'EXERCÍCIO'}</span></div>
        <div class="exercise-tools"><button class="report-exercise">⚑ Notificar erro</button>${step ? '' : `<span class="difficulty" aria-label="Dificuldade">${'●'.repeat(ex.difficulty || 1)}${'○'.repeat(Math.max(0, 3 - (ex.difficulty || 1)))}</span>`}</div>
      </div>
      <p class="instruction">${escapeHtml(ex.instruction || defaultInstruction(ex))}</p>
      ${ex.unit_id === 'lexical_minimum_morphology' ? `<div class="solve-steps"><b>Antes de responder:</b><span>1 · confirme caso e número</span><span>2 · reconheça a família da palavra</span><span>3 · aplique a terminação</span></div>` : ''}
      ${ex.type === 'listening' ? `<div class="listening-control"><button type="button" class="primary listen-button" data-speed="1">🔊 Ouvir</button><button type="button" class="secondary listen-slow" data-speed="0.78">Ouvir devagar</button><span class="muted listening-hint">0 reproduções${ex.voice ? ` · ${VOICE_NAMES[ex.voice] || ''}` : ''}</span></div>` : ''}
      ${ex.type === 'dialogue' ? `${ex.setting ? `<p class="dialogue-setting">${escapeHtml(ex.setting)}</p>` : ''}${dialogueBlockMarkup(ex.lines || [], { transcript: false, allowText: false })}` : ''}
      ${ex.type === 'dialogue_review' ? `${dialogueBlockMarkup(ex.lines || [], { transcript: true, highlights: ex.highlights || [] })}` : ''}
      ${UNGRADED.has(ex.type) ? '' : `<h2 class="prompt">${interactiveRussianText(ex.prompt || ex.front || '')}</h2>`}
      ${!['listening', 'dialogue'].includes(ex.type) && !UNGRADED.has(ex.type) && state.courseId === 'russian' ? `<p class="prompt-help">Clique em uma palavra russa para ouvir e abrir o dicionário.</p>` : ''}
      ${ex.context ? `<div class="context">${interactiveRussianText(ex.context)}</div>` : ''}
      <div id="responseArea">${responseMarkup(ex)}</div>
      <div id="feedbackArea"></div>
    </article>`;
  $('.quit-session').addEventListener('click', exitSession);
  $('.map-session')?.addEventListener('click', openSessionMap);
  $('.report-exercise').addEventListener('click', () => openReportDialog(ex));
  bindInteractiveWords();
  bindResponseEvents(ex);
  if (ex.type === 'listening') {
    const listenButton = $('.listen-button');
    const slowButton = $('.listen-slow');
    let plays = 0;
    const playAudio = button => {
      plays += 1;
      $('.listening-hint').textContent = `${plays} ${plays === 1 ? 'reprodução' : 'reproduções'}`;
      speakText(ex.audio_text || '', button, Number(button.dataset.speed || 1), ex.voice || '');
    };
    listenButton.addEventListener('click', () => playAudio(listenButton));
    slowButton.addEventListener('click', () => playAudio(slowButton));
  }
  if (ex.type === 'dialogue' || ex.type === 'dialogue_review') {
    const player = bindDialogueBlock($(state.sessionHost), ex.lines || []);
    if (ex.type === 'dialogue_review' && player) player.play(1);
  }
  if (ex.type === 'vocab_card') {
    $$('.vc-speak').forEach(button => button.addEventListener('click', () => speakText(button.dataset.text, button, 1, button.dataset.voice || '')));
    const auto = $('.vc-speak[data-autoplay="1"]');
    if (auto) speakText(auto.dataset.text, auto);
  }
  if (UNGRADED.has(ex.type)) {
    $('.continue-ungraded')?.addEventListener('click', () => { stopAllAudio(); nextExercise(); });
  }
  persistSession();
}

function phaseLabel(ex, index) {
  if (state.courseId === 'romanian') {
    if (['reading', 'listening'].includes(ex.type)) return '1 · OUVIR E NOTAR';
    if (ex.type === 'flashcard' || ['recall', 'retrieval'].includes(ex.stage)) return '2 · RECUPERAR';
    if (ex.type === 'open_text' || ['micro_writing', 'speaking_plan', 'transfer'].includes(ex.stage)) return '4 · CONVERSAR';
    return '3 · PRATICAR';
  }
  if (ex.type === 'flashcard' || ['recall', 'retrieval', 'spaced_review'].includes(ex.stage)) return '1 · RECUPERAR';
  if (['reading', 'listening'].includes(ex.type)) return '2 · COMPREENDER';
  if (ex.type === 'open_text' || ['construction', 'writing_b2', 'micro_writing', 'speaking_plan', 'transfer'].includes(ex.stage)) return '4 · PRODUZIR';
  return index < 4 ? '1 · RECUPERAR' : '3 · PRATICAR';
}

function defaultInstruction(ex) {
  const type = ex.type;
  if (type === 'listening' && ex.response_type === 'input') return 'Ouça e digite exatamente o que ouviu.';
  return ({
    choice: 'Escolha a alternativa adequada.',
    input: 'Digite a construção completa.',
    correction: 'Reescreva a frase corrigindo apenas o necessário.',
    sentence_order: 'Monte uma frase natural com todos os blocos.',
    flashcard: 'Recupere a resposta antes de virar o cartão.',
    open_text: `Escreva sua resposta em ${state.courseId === 'romanian' ? 'romeno' : state.courseId === 'kazakh' ? 'cazaque' : 'russo'}.`,
    match_pairs: 'Clique em um item da esquerda e depois no par correspondente à direita.',
    reading: 'Leia o texto e responda com base nele.',
    listening: 'Ouça o áudio (pode repetir quantas vezes quiser) e escolha a alternativa correta.',
    dialogue: 'Ouça o diálogo e responda.',
  })[type] || 'Responda à questão.';
}

function responseMarkup(ex) {
  if (ex.type === 'listening' && ex.response_type === 'input') {
    return `<div class="answer-row"><input id="textAnswer" type="text" autocomplete="off" spellcheck="false" placeholder="Digite exatamente o que ouviu…"><button class="primary submit-answer">Verificar</button></div>${characterPadMarkup('textAnswer')}`;
  }
  if (ex.type === 'vocab_card') return vocabCardMarkup(ex);
  if (ex.type === 'dialogue_review') return '<div class="continue-row"><button class="primary continue-ungraded">Continuar</button></div>';
  if (ex.type === 'choice' || ex.type === 'reading' || ex.type === 'listening' || ex.type === 'dialogue') {
    return `<div class="options">${ex.options.map((option, index) => `<button class="option" data-shortcut="${index + 1}" aria-pressed="false" data-answer="${escapeHtml(option)}">${escapeHtml(option)}</button>`).join('')}</div>
      <p class="keyboard-hint">1–4: escolher · Enter: confirmar ou avançar</p><div class="continue-row"><button class="primary submit-answer" disabled>Confirmar</button></div>`;
  }
  if (ex.type === 'input') {
    const language = state.courseId === 'romanian' ? 'romeno' : state.courseId === 'kazakh' ? 'cazaque' : 'russo';
    return `<div class="answer-row"><input id="textAnswer" type="text" autocomplete="off" spellcheck="false" placeholder="Digite em ${language}…"><button class="primary submit-answer">Verificar</button></div>${characterPadMarkup('textAnswer')}`;
  }
  if (ex.type === 'correction') {
    return `<div class="answer-row"><textarea id="textAnswer" autocomplete="off" spellcheck="false" placeholder="Reescreva aqui a frase completa já corrigida…"></textarea><button class="primary submit-answer">Verificar</button></div>${characterPadMarkup('textAnswer')}`;
  }
  if (ex.type === 'sentence_order') {
    const shuffledOrder = shuffle(ex.tokens.map((_, index) => index));
    return `<div class="built-sentence" id="builtSentence"><span class="muted">Clique nos blocos abaixo${ex.extra_block ? '; um deles sobra' : ''}.</span></div>
      <div class="tokens" id="tokenBank">${shuffledOrder.map(index => `<button class="token" data-index="${index}">${escapeHtml(ex.tokens[index])}</button>`).join('')}</div>
      <div class="continue-row"><button class="primary submit-answer" disabled>Verificar</button></div>`;
  }
  if (ex.type === 'flashcard') {
    return `<div class="flashcard-front"><p>Responda mentalmente ou em voz alta.</p><button class="primary reveal-card">Mostrar resposta</button></div><div id="flashcardReveal"></div>`;
  }
  if (ex.type === 'open_text') {
    const placeholder = state.courseId === 'romanian' ? 'Scrieți aici…' : state.courseId === 'kazakh' ? 'Осында жазыңыз…' : 'Пишите здесь…';
    return `<textarea class="writing-area" id="writingAnswer" spellcheck="false" placeholder="${placeholder}"></textarea>
      ${characterPadMarkup('writingAnswer')}
      <div class="writing-tools"><span id="wordCount">0 palavras</span><span>O texto será salvo para correção posterior.</span></div>
      <button class="primary submit-answer">Salvar produção</button>`;
  }
  if (ex.type === 'match_pairs') {
    return `<div class="match-pairs">
        <div class="match-column">${ex.left_items.map((item, index) => `<button class="match-item" data-side="left" data-index="${index}">${escapeHtml(item)}</button>`).join('')}</div>
        <div class="match-column">${ex.right_items.map((item, index) => `<button class="match-item" data-side="right" data-index="${index}">${escapeHtml(item)}</button>`).join('')}</div>
      </div>
      <div class="match-pairs-list" id="matchPairsList"><span class="muted">Selecione um item de cada coluna para conectar.</span></div>
      <div class="continue-row"><button class="primary submit-answer" disabled>Verificar</button></div>`;
  }
  return '';
}

function characterPadMarkup(targetId) {
  if (state.courseId !== 'romanian') return '';
  const characters = ['ă', 'â', 'î', 'ș', 'ț', 'Ă', 'Â', 'Î', 'Ș', 'Ț'];
  return `<div class="character-pad" aria-label="Teclado de diacríticos romenos">
    <span>Inserir:</span>${characters.map(char => `<button type="button" data-char="${char}" data-target="${targetId}">${char}</button>`).join('')}
  </div>`;
}

function bindCharacterPad() {
  $$('.character-pad button').forEach(button => button.addEventListener('click', () => {
    const input = $(`#${button.dataset.target}`);
    if (!input) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    input.setRangeText(button.dataset.char, start, end, 'end');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  }));
}

function renderMatchedPairs(ex) {
  const list = $('#matchPairsList');
  list.innerHTML = state.matchedPairs.length ? state.matchedPairs.map((pair, index) => `<div class="matched-pair">
      <span>${escapeHtml(pair.left)}</span><i>→</i><span>${escapeHtml(pair.right)}</span>
      <button class="remove-pair" type="button" data-index="${index}" title="Desfazer">×</button>
    </div>`).join('') : '<span class="muted">Selecione um item de cada coluna para conectar.</span>';
  $$('.remove-pair', list).forEach(button => button.addEventListener('click', () => {
    const [removed] = state.matchedPairs.splice(Number(button.dataset.index), 1);
    $$('.match-item[data-side="left"]').forEach(item => {
      if (ex.left_items[Number(item.dataset.index)] === removed.left) { item.disabled = false; item.classList.remove('matched'); }
    });
    $$('.match-item[data-side="right"]').forEach(item => {
      if (ex.right_items[Number(item.dataset.index)] === removed.right) { item.disabled = false; item.classList.remove('matched'); }
    });
    renderMatchedPairs(ex);
  }));
  $('.submit-answer').disabled = state.matchedPairs.length !== ex.left_items.length;
}

function bindResponseEvents(ex) {
  state.responseKeys?.abort();
  state.responseKeys = new AbortController();
  document.addEventListener('keydown', event => {
    if (!$(state.sessionHost)?.closest('.view.active') || $('dialog[open]') || $('.sidebar.open')) return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return;
    if (event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    const options = $$('.option', $(state.sessionHost));
    if (/^[1-4]$/.test(event.key) && options.length && !options[0].disabled) {
      const option = options[Number(event.key) - 1];
      if (option) { event.preventDefault(); option.click(); option.focus(); }
    } else if (['ArrowDown', 'ArrowUp'].includes(event.key) && event.target.classList.contains('option')) {
      const step = event.key === 'ArrowDown' ? 1 : -1;
      event.preventDefault();
      options[(options.indexOf(event.target) + step + options.length) % options.length].focus();
    } else if (event.key === 'Enter') {
      const next = $('.next-exercise, .continue-ungraded', $(state.sessionHost));
      const submit = $('.submit-answer', $(state.sessionHost));
      // Enter on unrelated controls retains its native action.
      if (event.target.tagName === 'BUTTON' && !event.target.matches('.option, .submit-answer, .next-exercise, .continue-ungraded')) return;
      const target = next || (submit && !submit.disabled ? submit : null);
      if (target) { event.preventDefault(); target.click(); }
    }
  }, { signal: state.responseKeys.signal });
  bindCharacterPad();
  $$('.option').forEach(button => button.addEventListener('click', () => {
    $$('.option').forEach(item => { item.classList.remove('selected'); item.setAttribute('aria-pressed', 'false'); });
    button.classList.add('selected');
    button.setAttribute('aria-pressed', 'true');
    state.selectedAnswer = button.dataset.answer;
    $('.submit-answer').disabled = false;
    if (ex.speak_options !== false) speakText(button.dataset.answer, button);
  }));

  if ($('#textAnswer')) {
    $('#textAnswer').focus();
    $('#textAnswer').addEventListener('keydown', event => {
      if (event.key === 'Enter' && ex.type !== 'correction') submitCurrent(ex, $('#textAnswer').value);
    });
  }

  $$('.token').forEach(button => button.addEventListener('click', () => {
    const index = Number(button.dataset.index);
    state.builtTokens.push({ index, text: ex.tokens[index] });
    button.disabled = true;
    renderBuiltSentence();
  }));

  if ($('#writingAnswer')) {
    $('#writingAnswer').focus();
    $('#writingAnswer').addEventListener('input', () => {
      const count = countWords($('#writingAnswer').value);
      $('#wordCount').textContent = `${count} ${count === 1 ? 'palavra' : 'palavras'}`;
    });
  }

  if (ex.type === 'match_pairs') {
    $$('.match-item').forEach(button => button.addEventListener('click', () => {
      if (button.disabled) return;
      if (button.dataset.side === 'left') {
        $$('.match-item[data-side="left"]').forEach(item => item.classList.remove('selected'));
        button.classList.add('selected');
        state.matchSelectedLeft = button;
      } else {
        if (!state.matchSelectedLeft) { showToast('Escolha primeiro um item da coluna esquerda.'); return; }
        const leftButton = state.matchSelectedLeft;
        const left = ex.left_items[Number(leftButton.dataset.index)];
        const right = ex.right_items[Number(button.dataset.index)];
        state.matchedPairs.push({ left, right });
        leftButton.disabled = true;
        leftButton.classList.remove('selected');
        leftButton.classList.add('matched');
        button.disabled = true;
        button.classList.add('matched');
        state.matchSelectedLeft = null;
        renderMatchedPairs(ex);
      }
    }));
  }

  if ($('.reveal-card')) $('.reveal-card').addEventListener('click', () => revealFlashcard(ex));
  if ($('.submit-answer')) $('.submit-answer').addEventListener('click', () => {
    let answer = state.selectedAnswer;
    if ($('#textAnswer')) answer = $('#textAnswer').value;
    if ($('#writingAnswer')) answer = $('#writingAnswer').value;
    if (ex.type === 'sentence_order') answer = state.builtTokens.map(item => item.text).join(' ');
    if (ex.type === 'match_pairs') answer = state.matchedPairs;
    submitCurrent(ex, answer);
  });
}

function renderBuiltSentence() {
  const target = $('#builtSentence');
  target.innerHTML = state.builtTokens.length ? state.builtTokens.map((item, position) =>
    `<button class="token" data-position="${position}" title="Remover">${escapeHtml(item.text)}</button>`
  ).join('') : '<span class="muted">Clique nos blocos abaixo.</span>';
  $$('.token', target).forEach(button => button.addEventListener('click', () => {
    const [removed] = state.builtTokens.splice(Number(button.dataset.position), 1);
    $(`#tokenBank .token[data-index="${removed.index}"]`).disabled = false;
    renderBuiltSentence();
  }));
  $('.submit-answer').disabled = state.builtTokens.length === 0;
}

async function revealFlashcard(ex) {
  const data = await api(`/api/reveal?id=${encodeURIComponent(ex.id)}`);
  $('#flashcardReveal').innerHTML = `<div class="flashcard-back"><b>${escapeHtml(data.back)}</b>${data.explanation ? `<p>${escapeHtml(data.explanation)}</p>` : ''}<button type="button" class="secondary speak-card">🔊 Ouvir resposta</button></div>
    <div class="rating-buttons">
      <button data-rating="1">Errei</button><button data-rating="2">Difícil</button>
      <button data-rating="3">Lembrei</button><button data-rating="4">Fácil</button>
    </div>`;
  $('.reveal-card').disabled = true;
  $('.speak-card').addEventListener('click', event => speakText(data.back, event.currentTarget));
  $$('.rating-buttons button').forEach(button => button.addEventListener('click', () =>
    submitCurrent(ex, data.back, Number(button.dataset.rating))
  ));
}

function countWords(text) {
  return (text.trim().match(/[\p{L}\p{N}-]+/gu) || []).length;
}

async function submitCurrent(ex, answer, rating = null) {
  const isEmpty = ex.type === 'match_pairs' ? !Array.isArray(answer) || answer.length === 0 : String(answer || '').trim() === '';
  if (isEmpty && ex.type !== 'flashcard') {
    showToast('Digite ou selecione uma resposta.');
    return;
  }
  $$('.submit-answer, .option, #textAnswer, #writingAnswer, .token, .match-item, .remove-pair, .rating-buttons button').forEach(el => el.disabled = true);
  const result = await api('/api/answer', {
    method: 'POST',
    body: JSON.stringify({
      exercise_id: ex.id,
      answer,
      rating,
      response_format: ex.type,
      course_id: state.courseId,
      mode: state.sessionMode,
      consultation: state.consultation,
      session_id: state.sessionId,
      response_ms: Math.round(performance.now() - state.startedAt),
    }),
  });
  state.summary = result.summary;
  const { summary: _summary, ...slimResult } = result;
  state.results.push({ ...slimResult, exercise_id: ex.id, retry: Boolean(ex.retry), prompt: ex.prompt || ex.head || '' });
  updateItemStatus(result);
  const requeued = queueVocabRetry(ex, result);
  persistSession();
  renderDashboard();
  renderFeedback(result, ex, requeued);
}

function renderFeedback(result, ex, requeued = false) {
  const pending = result.is_correct == null;
  const css = pending ? 'pending' : result.is_correct ? 'correct' : result.is_partial ? 'partial' : 'incorrect';
  let details = '';
  if (!pending && !result.is_correct) {
    const label = ['listening', 'dialogue', 'reading'].includes(ex.type) && !/[А-Яа-яЁё]/.test(result.correct_answer || '') ? 'Resposta esperada:' : 'Forma esperada:';
    details += `<p>${label}</p><p class="expected">${escapeHtml(result.correct_answer)}</p>`;
  }
  if (!pending && result.proximity_note) details += `<p><b>Crédito: ${Math.round((result.score || 0) * 100)}%.</b> ${escapeHtml(result.proximity_note)}</p>`;
  if (ex.unit_id === 'lexical_minimum_morphology' && ex.stem != null && ex.ending != null) {
    details += `<div class="morph-feedback"><span>FORMA CONSTRUÍDA</span><strong><i>${escapeHtml(ex.stem)}</i><u>${escapeHtml(ex.ending || '∅')}</u></strong><small>${escapeHtml(ex.case_ru || '')}${ex.number_code ? ` · ${ex.number_code === 'pl' ? 'plural' : 'singular'}` : ''}</small></div>`;
  }
  if (result.explanation) details += `<p>${escapeHtml(result.explanation)}</p>`;
  if (ex.type === 'listening' && result.transcript) details += `<details class="transcript"${ex.lesson_id ? ' open' : ''}><summary>Ver transcrição</summary><p>${interactiveRussianText(result.transcript)}</p></details>`;
  if (ex.type === 'dialogue') details += `<details class="transcript"><summary>Ver o diálogo com texto</summary>${dialogueBlockMarkup(ex.lines || [], { transcript: true, highlights: ex.highlights || [] })}</details>`;
  if (result.after_audio?.text) details += `<p class="after-audio"><button type="button" class="secondary replay-correct" data-text="${escapeHtml(result.after_audio.text)}" data-voice="${escapeHtml(result.after_audio.voice || '')}">🔊 Ouvir a forma correta</button> <span>${interactiveRussianText(result.after_audio.text)}</span></p>`;
  if (requeued) details += '<p class="retry-note">↻ Este item volta daqui a algumas telas. A lição permite até duas novas tentativas por construção e uma por pergunta de diálogo.</p>';
  if (pending) details += `<p>${result.word_count} palavras registradas.</p>`;
  // Na aula não há pergunta extra depois do erro: a explicação já vem acima e a aula segue.
  if (!pending && !result.is_correct && state.sessionMode !== 'lesson') details += classificationMarkup(result.attempt_id, ex);
  $('#feedbackArea').innerHTML = `<div class="feedback-box ${css}" role="status" aria-live="polite" tabindex="-1">
    <h4><span class="feedback-icon" aria-hidden="true">${pending ? '◷' : result.is_correct ? '✓' : result.is_partial ? '≈' : '×'}</span>${pending ? 'Salvo' : result.is_correct ? 'Correto' : result.is_partial ? 'Quase' : 'Ainda não'}</h4>${details}
  </div><div class="continue-row"><button class="primary next-exercise">${state.current + 1 === state.queue.length ? 'Ver resultado' : 'Próximo item'}</button></div>`;
  $('.feedback-box').focus({ preventScroll: true });
  bindClassification(result.attempt_id);
  bindInteractiveWords();
  const transcriptPlayer = $('#feedbackArea .dialogue-block') ? bindDialogueBlock($('#feedbackArea'), ex.lines || []) : null;
  const replay = $('.replay-correct');
  if (replay) {
    replay.addEventListener('click', () => speakText(replay.dataset.text, replay, 1, replay.dataset.voice));
    // Ouvir a forma certa logo depois do feedback fixa o input correto,
    // em vez de deixar o distrator como última forma vista.
    if (ex.lesson_id && !transcriptPlayer) speakText(replay.dataset.text, replay, 1, replay.dataset.voice);
  }
  $('.next-exercise').addEventListener('click', () => { stopAllAudio(); nextExercise(); });
}

function classificationMarkup(attemptId, ex = {}) {
  const labels = activeErrorLabels();
  if (['listening', 'dialogue'].includes(ex.type) && !labels.pronuncia) labels.pronuncia = 'Não entendi o áudio';
  return `<div class="self-classify"><p>O que aconteceu? Isso melhora o diagnóstico.</p><div class="classification-buttons" data-attempt="${attemptId}">
    ${Object.entries(labels).map(([key, label]) => `<button data-category="${key}">${label}</button>`).join('')}
  </div></div>`;
}

function bindClassification(attemptId) {
  if (!attemptId || !$('.classification-buttons')) return;
  $$('.classification-buttons button').forEach(button => button.addEventListener('click', async () => {
    await api('/api/classify', { method: 'POST', body: JSON.stringify({ attempt_id: attemptId, category: button.dataset.category }) });
    $$('.classification-buttons button').forEach(item => item.classList.remove('chosen'));
    button.classList.add('chosen');
    state.summary = await api(`/api/summary?course_id=${encodeURIComponent(state.courseId)}`);
    renderDashboard();
  }));
}

function nextExercise() {
  const finished = state.queue[state.current];
  if (finished && (UNGRADED.has(finished.type) || LESSON_SCREENS.has(finished.type)) && state.itemStatus[state.current] === 'new') state.itemStatus[state.current] = 'seen';
  state.current += 1;
  if (state.current >= state.queue.length) renderSessionComplete();
  else renderExercise();
}

function renderVocabComplete() {
  completeTracking();
  const first = state.results.filter(item => item.is_correct != null && !item.retry);
  const retries = state.results.filter(item => item.retry);
  const firstPoints = first.reduce((sum, item) => sum + Number(item.score || 0), 0);
  const firstScore = first.length ? Math.round(100 * firstPoints / first.length) : 0;
  const recovered = retries.filter(item => item.is_correct).length;
  const missed = [...new Map(state.results.filter(item => item.is_correct === false && !item.retry)
    .map(item => [item.exercise_id, item])).values()];
  const stillWrong = missed.filter(item => !state.results.some(other => other.retry && other.exercise_id === item.exercise_id && other.is_correct));
  const verdict = !first.length ? 'Parte sem tarefas corrigidas.'
    : firstScore >= 90 ? 'Recuperação sólida na primeira tentativa. O próximo passo é a revisão espaçada: volte amanhã.'
    : firstScore >= 70 ? 'Base razoável, mas ainda instável: os erros abaixo precisam voltar na revisão de amanhã.'
    : 'Ainda abaixo do necessário. Refaça esta parte amanhã antes de avançar; releia os cartões das construções abaixo.';
  const nextPart = { 1: '2', 2: '3' }[state.vocabPart];
  $(state.sessionHost).innerHTML = `<article class="panel session-complete">
    <p class="eyebrow">LIÇÃO · ${state.vocabPart === 'all' ? 'COMPLETA' : `PARTE ${escapeHtml(state.vocabPart)}`}</p>
    <div class="result-ring" style="--score:${firstScore}%"><b>${first.length ? `${firstScore}%` : '—'}</b></div>
    <h2>${first.length} respostas na 1ª tentativa · ${recovered}/${retries.length} recuperadas depois</h2>
    <p>${escapeHtml(verdict)}</p>
    ${missed.length ? `<div class="vocab-missed"><p class="eyebrow">ERRADAS NA PRIMEIRA TENTATIVA</p><ul>${missed.map(item => `<li class="${stillWrong.includes(item) ? 'still-wrong' : ''}"><span>${interactiveRussianText(item.prompt)}</span><b>${escapeHtml(item.correct_answer || '')}</b></li>`).join('')}</ul></div>` : ''}
    <div class="hero-actions" style="justify-content:center">
      ${nextPart ? `<button class="primary vocab-next-part">Continuar: Parte ${nextPart}</button>` : ''}
      <button class="${nextPart ? 'secondary' : 'primary'} session-again">Voltar à lição</button>
    </div>
  </article>`;
  bindInteractiveWords();
  const lessonId = state.vocabLesson?.id;
  $('.vocab-next-part')?.addEventListener('click', () => startVocabSession(lessonId, nextPart));
  $('.session-again').addEventListener('click', quitSession);
}

function renderSessionComplete() {
  if (state.sessionMode === 'lesson') { renderLessonComplete(); return; }
  completeTracking();
  if (state.sessionMode === 'vocab_lesson') { renderVocabComplete(); return; }
  const graded = state.results.filter(item => item.is_correct != null);
  const correct = graded.filter(item => item.is_correct).length;
  const partial = graded.filter(item => item.is_partial).length;
  const points = graded.reduce((sum, item) => sum + Number(item.score || 0), 0);
  const score = graded.length ? Math.round(100 * points / graded.length) : 100;
  $(state.sessionHost).innerHTML = `<article class="panel session-complete">
    <p class="eyebrow">SESSÃO CONCLUÍDA</p>
    <div class="result-ring" style="--score:${score}%"><b>${graded.length ? `${score}%` : 'Salvo'}</b></div>
    <h2>${graded.length ? `${correct} exatas · ${partial} parciais · ${graded.length} respostas` : 'Produção registrada'}</h2>
    <p class="muted">O resultado já entrou no histórico e na fila de revisão espaçada.</p>
    <div class="hero-actions" style="justify-content:center">
      <button class="primary session-home">Voltar ao painel</button>
      <button class="secondary session-again">Nova sessão</button>
    </div>
  </article>`;
  $('.session-home').addEventListener('click', () => { quitSession({ silent: true }); setView('home'); });
  $('.session-again').addEventListener('click', () => quitSession());
}

function quitSession({ silent = false } = {}) {
  state.warmAudioController?.abort();
  state.responseKeys?.abort();
  state.queue = [];
  const host = $(state.sessionHost);
  host.innerHTML = '';
  if (state.sessionHost === '#lessonArea') {
    state.sessionHost = '#sessionArea';
    if (!silent) setView('home');
    return;
  }
  host.classList.add('hidden');
  if (state.sessionHost === '#morphologyGameArea') {
    $('#morphologyContent').classList.remove('hidden');
    state.sessionHost = '#sessionArea';
    loadMorphology();
  } else if (state.sessionHost === '#prefixGameArea') {
    $('#prefixesContent').classList.remove('hidden');
    state.sessionHost = '#sessionArea';
    loadPrefixes();
  } else if (state.sessionHost === '#vocabGameArea') {
    stopAllAudio();
    $('#vocabContent').classList.remove('hidden');
    state.sessionHost = '#sessionArea';
    loadVocab();
  } else if (!silent) {
    setView('practice');
  }
}

function applyCourseInterface() {
  const config = currentConfig();
  document.body.dataset.course = state.courseId;
  document.title = 'Русский тренажёр';
  $('#brandMark').textContent = config.mark;
  $('#brandName').textContent = config.brand;
  $('#brandLevel').textContent = config.level;
  $('#referenceTitle').textContent = config.referenceTitle;
  $('#referenceCopy').textContent = config.referenceCopy;
}

function bindGlobalEvents() {
  window.addEventListener('pagehide', () => persistSession({ keepalive: true }));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') persistSession({ keepalive: true });
  });
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  const setMenu = open => {
    $('.sidebar').classList.toggle('open', open);
    $('#sidebarBackdrop').classList.toggle('hidden', !open);
    $('#mobileMenu').setAttribute('aria-expanded', String(open));
  };
  $('#mobileMenu').addEventListener('click', () => {
    const open = !$('.sidebar').classList.contains('open');
    setMenu(open);
    if (open) $('.sidebar .nav-item').focus();
  });
  $('#sidebarBackdrop').addEventListener('click', () => setMenu(false));
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && $('.sidebar.open')) { setMenu(false); $('#mobileMenu').focus(); }
  });
  const themeSelect = $('#themeSelect');
  themeSelect.value = document.documentElement.dataset.themeChoice || 'dark';
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');
  const applyTheme = () => {
    const choice = themeSelect.value;
    document.documentElement.dataset.themeChoice = choice;
    document.documentElement.dataset.theme = choice === 'system' ? (systemTheme.matches ? 'dark' : 'light') : choice;
  };
  themeSelect.addEventListener('change', () => { savePreference('lingualab-theme', themeSelect.value); applyTheme(); });
  systemTheme.addEventListener('change', applyTheme);
  $('#backToPractice').addEventListener('click', () => {
    if (state.queue.length && state.sessionKey) exitSession();
    else { if (state.queue.length) quitSession({ silent: true }); setView('practice'); }
  });
  $('#morphKind').addEventListener('change', syncMorphFilters);
  $('#startMorphGame').addEventListener('click', startMorphologyGame);
  $('#startPrefixAll').addEventListener('click', () => startPrefixSession('all'));
  syncMorphFilters();
  $('#exportNow').addEventListener('click', async () => {
    const data = await api('/api/export', { method: 'POST', body: '{}' });
    $('#exportStatus').textContent = `Atualizado: ${data.files.join(', ')}`;
  });
  $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => {
    $(`#${button.dataset.closeDialog}`).close();
  }));
  $('#submitReport').addEventListener('click', async () => {
    const ex = state.reportExercise;
    if (!ex) return;
    const answer = $('#textAnswer')?.value || $('#writingAnswer')?.value || state.selectedAnswer || '';
    const result = await api('/api/report', {
      method: 'POST',
      body: JSON.stringify({
        exercise_id: ex.id,
        reason: $('#reportReason').value,
        note: $('#reportNote').value,
        answer,
        session_id: state.sessionId,
      }),
    });
    $('#reportDialog').close();
    state.summary = await api(`/api/summary?course_id=${encodeURIComponent(state.courseId)}`);
    renderDashboard();
    showToast(`Problema #${result.report_id} salvo para revisão.`);
  });
}

const updateUi = { info: null, busy: false };

function renderUpdate(message = '', buttonLabel = null, ready = false, disabled = false) {
  const button = $('#updateButton');
  $('#updateVersion').textContent = `Versão ${state.bootstrap.app_version}`;
  $('#updateMessage').textContent = message;
  button.textContent = buttonLabel || 'Buscar atualizações';
  button.classList.toggle('ready', ready);
  button.disabled = disabled;
}

async function checkUpdate(force) {
  renderUpdate('Verificando…', null, false, true);
  try {
    const info = await api(`/api/update/check${force ? '?force=1' : ''}`);
    updateUi.info = info;
    if (info.available && state.bootstrap.features.self_update) {
      renderUpdate(`Nova versão ${info.latest} disponível.`, `Atualizar para ${info.latest}`, true);
    } else if (info.available) {
      renderUpdate(`Versão ${info.latest} disponível (use o aplicativo instalado para atualizar).`);
    } else if (info.error) {
      renderUpdate(force ? info.error : '');
    } else {
      renderUpdate('Você está na versão mais recente.');
    }
  } catch (error) {
    renderUpdate(force ? error.message : '');
  }
}

async function applyUpdate() {
  if (!window.confirm(`Atualizar para a versão ${updateUi.info.latest}? O aplicativo vai fechar e reabrir sozinho. Seu progresso é mantido.`)) return;
  updateUi.busy = true;
  renderUpdate('Iniciando…', 'Atualizando…', false, true);
  try {
    await api('/api/update/apply', { method: 'POST', body: '{}' });
  } catch (error) {
    updateUi.busy = false;
    renderUpdate(error.message, `Atualizar para ${updateUi.info.latest}`, true);
    return;
  }
  const timer = window.setInterval(async () => {
    try {
      const status = await api('/api/update/status');
      if (status.phase === 'downloading') {
        const pct = status.total ? Math.round(100 * status.done / status.total) : 0;
        renderUpdate(`Baixando… ${pct}%`, 'Atualizando…', false, true);
      } else if (status.phase === 'installing') {
        renderUpdate('Instalando…', 'Atualizando…', false, true);
      } else if (status.phase === 'restarting') {
        renderUpdate('Reiniciando o aplicativo…', 'Atualizando…', false, true);
      } else if (status.phase === 'error') {
        window.clearInterval(timer);
        updateUi.busy = false;
        renderUpdate(status.error, `Atualizar para ${updateUi.info.latest}`, true);
      }
    } catch (_) {
      // O servidor fechou para trocar os arquivos; espera ele voltar e recarrega a página.
      renderUpdate('Reiniciando o aplicativo…', 'Atualizando…', false, true);
      window.clearInterval(timer);
      const wait = window.setInterval(async () => {
        try { await fetch('/api/update/status'); window.clearInterval(wait); window.location.reload(); } catch (_) { /* ainda reiniciando */ }
      }, 1500);
    }
  }, 700);
}

function bindUpdate() {
  renderUpdate();
  $('#updateButton').addEventListener('click', () => {
    if (updateUi.busy) return;
    if (updateUi.info && updateUi.info.available && state.bootstrap.features.self_update) applyUpdate();
    else checkUpdate(true);
  });
  checkUpdate(false);
}

async function init() {
  try {
    state.bootstrap = await api('/api/bootstrap?course_id=russian');
    state.summary = state.bootstrap.summary;
    state.sessionId = state.bootstrap.session_id;
    applyCourseInterface();
    renderDashboard();
    renderReference();
    bindGlobalEvents();
    bindUpdate();
    loadActiveSessions();
    api('/api/vocab/bootstrap').then(data => { state.vocabData = data; }).catch(() => {});
    const requestedView = new URLSearchParams(window.location.search).get('view');
    if (requestedView && baseViewMeta[requestedView]) setView(requestedView);
  } catch (error) {
    document.body.innerHTML = `<main style="padding:40px;font-family:system-ui"><h1>Não foi possível iniciar</h1><p>${escapeHtml(error.message)}</p></main>`;
  }
}

init();
