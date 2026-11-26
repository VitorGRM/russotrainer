"""Curso de francês (B1 → C1): trilha gramatical, eixos temáticos, conjugação e caderno de erros.

O conteúdo fica em data/fr/ (ver tools/validate_french.py para o formato):
    units/*.json   {"units": [UNIDADE, ...]}  regras + exercícios de cada unidade da trilha
    themes/*.json  {"themes": [EIXO, ...]}    vocabulário por eixo temático
    verbs.json     {"verbs": [VERBO, ...]}    os verbos prioritários, conjugados por conjugate()

Princípio do curso: errar não custa nada. Cada resposta errada abre uma escada de ajuda (sinal →
pista → resposta) e o aluno tenta de novo; o acerto com ajuda vale menos XP, mas vale. O XP nunca
diminui. A revisão espaçada recua um estágio no erro, mas lembra o melhor estágio já alcançado e
recupera depressa.

O progresso fica em tabelas fr_* do mesmo banco do curso de russo.
"""

from __future__ import annotations

import difflib
import json
import random
import re
import secrets
import sqlite3
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

INTERVALS = [timedelta(minutes=10), timedelta(days=1), timedelta(days=3), timedelta(days=7),
             timedelta(days=14), timedelta(days=30), timedelta(days=60), timedelta(days=120), timedelta(days=240)]
MASTERED_STAGE = 4

CATEGORIES = {
    "G1": "Determinantes (artigo, partitivo, de)",
    "G2": "Preposições e regência",
    "G3": "Pronomes e relativos",
    "G4": "Concordância",
    "G5": "Tempos e modos",
    "C": "Conjugação",
    "L1": "Falsos cognatos e calques",
    "L2": "Léxico preciso",
    "R": "Registro",
    "O": "Ortografia",
}
# Primeiro degrau da escada de ajuda: aponta onde olhar, sem dar a regra.
SIGNALS = {
    "G1": "Quase. Confira o determinante (artigo, partitivo ou de).",
    "G2": "Quase. Confira a preposição.",
    "G3": "Quase. Confira o pronome.",
    "G4": "Quase. Confira a concordância (gênero, número, particípio).",
    "G5": "Quase. Confira o tempo ou o modo do verbo.",
    "C": "Quase. Confira a forma do verbo.",
    "L1": "Cuidado: pode ser um falso cognato ou uma tradução literal do português.",
    "L2": "Procure a palavra mais precisa para o contexto.",
    "R": "Pense no registro: quem fala com quem, e em que situação?",
    "O": "Confira a ortografia e os acentos.",
}
REGISTERS = {"familiar": "Familiar", "neutro": "Neutro", "formal": "Formal"}

PHASES = [
    {"n": 1, "title": "Consolidar", "level": "B1 → B1+", "goal": "Narrar, descrever e opinar sem os erros que denunciam o B1."},
    {"n": 2, "title": "Argumentar", "level": "B1+ → B2", "goal": "Defender um ponto de vista por escrito e oralmente, com nuance e registro certo."},
    {"n": 3, "title": "Refinar", "level": "B2 → C1", "goal": "Escolher entre construções equivalentes, sintetizar e soar natural."},
]
LEVEL_TITLES = ["Flâneur", "Promeneur", "Voyageur", "Explorateur", "Habitué", "Connaisseur", "Orateur",
                "Érudit", "Virtuose", "Immortel"]

XP_BY_TRY = {1: 10, 2: 6, 3: 3}
SCORE_BY_TRY = {1: 1.0, 2: 0.7, 3: 0.4}
XP_FAIL = 1          # tentar também conta
XP_RECOVERY = 5      # acertar algo que você tinha errado
XP_INTRO = 2

TYPE_ORDER = {"mc": 0, "pairs": 1, "register": 2, "order": 3, "gap": 4, "fix": 5, "transform": 6, "dict": 7}
APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "´": "'", "«": '"', "»": '"', "“": '"', "”": '"',
                             " ": " ", " ": " ", "œ": "oe", "Œ": "oe", "æ": "ae"})
WORD_RE = re.compile(r"[\wÀ-ÿœŒ'-]+")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None = None) -> str:
    return (moment or now_utc()).isoformat(timespec="seconds")


def today() -> str:
    return now_utc().astimezone().date().isoformat()


def norm(value: object) -> str:
    """Comparação tolerante a caixa, espaços, aspas tipográficas e pontuação final; NÃO a acentos."""
    text = unicodedata.normalize("NFC", str(value or "")).translate(APOSTROPHES).lower()
    text = re.sub(r"\s*'\s*", "'", text)
    text = re.sub(r"\s+([,;:!?.])", r"\1", text)
    text = re.sub(r"[\s.!?…;:,]+$", "", text)
    text = re.sub(r'^"+|"+$', "", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def slug(text: str) -> str:
    base = strip_accents(norm(text)).replace("'", "-")
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:60]


def shuffled(values: list) -> list:
    copy = list(values)
    random.shuffle(copy)
    return copy


def level_info(xp: int) -> dict:
    """Nível n exige 300·n·(n+1)/2 XP acumulado; cada nível fica um pouco mais longo."""
    level, need = 0, 0
    while xp >= need + 300 * (level + 1):
        need += 300 * (level + 1)
        level += 1
    span = 300 * (level + 1)
    title = LEVEL_TITLES[min(level, len(LEVEL_TITLES) - 1)]
    return {"level": level + 1, "title": title, "into": xp - need, "span": span}


# ============================================================================ conjugação
PRONOUNS = ["je", "tu", "il", "nous", "vous", "ils"]
PRONOUN_LABELS = ["je", "tu", "il / elle", "nous", "vous", "ils / elles"]
REFLEXIVE = ["me", "te", "se", "nous", "vous", "se"]
TENSES = {
    "pres": "présent", "pc": "passé composé", "imp": "imparfait", "pqp": "plus-que-parfait",
    "fut": "futur simple", "cond": "conditionnel présent", "condp": "conditionnel passé",
    "subj": "subjonctif présent", "impe": "impératif",
}
TENSE_PHASE = {"pres": 1, "pc": 1, "imp": 1, "fut": 1, "cond": 1, "subj": 1, "impe": 1, "pqp": 1, "condp": 2}
END_IMP = ["ais", "ais", "ait", "ions", "iez", "aient"]
END_FUT = ["ai", "as", "a", "ons", "ez", "ont"]
END_SUBJ = ["e", "es", "e", "ions", "iez", "ent"]
VOWELS = tuple("aeéèêëiîïoôuûüyh")
H_ASPIRE = {"haïr"}


def _elide(word: str, nxt: str, exceptions: set[str] = frozenset()) -> str:
    if word in ("je", "me", "te", "se") and nxt[:1].lower() in "aeéèêëiîïoôuûüyh" and nxt not in exceptions:
        if nxt.startswith("h") and nxt in H_ASPIRE:
            return word + " "
        return word[0] + "'"
    return word + " "


def _join(*parts: str) -> str:
    out = ""
    for index, part in enumerate(parts):
        if not part:
            continue
        nxt = next((p for p in parts[index + 1:] if p), "")
        if part in ("je", "me", "te", "se") and nxt:
            out += _elide(part, nxt)
        else:
            out += part + " "
    return out.strip()


def _imp_stem_fix(stem: str, ending: str) -> str:
    """Mange-ais, mais mang-ions; commenç-ais, mais commenc-ions."""
    if ending.startswith("i"):
        if stem.endswith("ge"):
            return stem[:-1]
        if stem.endswith("ç"):
            return stem[:-1] + "c"
    return stem


def _agree(pp: str, person: int, subject: str) -> list[str]:
    """Formas aceitas do particípio com être, conforme o sujeito mostrado."""
    fem = pp + "e"
    plur = pp if pp.endswith(("s", "x")) else pp + "s"
    fem_pl = fem + "s"
    if subject == "elle":
        return [fem]
    if subject == "elles":
        return [fem_pl]
    if subject in ("il", "ils"):
        return [pp] if subject == "il" else [plur]
    if person in (0, 1):
        return [pp, fem]
    if person == 3:
        return [plur, fem_pl]
    return [pp, fem, plur, fem_pl]  # vous: singular de cortesia ou plural


def conjugate(verb: dict) -> dict:
    """Tabela completa a partir do presente, do radical do futuro, do particípio e do auxiliar.

    Retorna {tempo: [forma por pessoa]} com a forma depois do sujeito (inclui pronome reflexivo e
    auxiliar). Impératif: [tu, nous, vous]. O auxiliar être concorda no masculino na forma canônica.
    """
    pres = verb["pres"]
    pron = bool(verb.get("pron"))
    aux = "être" if pron else verb.get("aux", "avoir")
    pp = verb["pp"]
    nous_stem = verb.get("imp_stem") or pres[3][:-3]
    fut = verb["fut"]
    if "subj_full" in verb:
        subj = list(verb["subj_full"])
    else:
        s1 = verb.get("subj", [None, None])[0] or pres[5][:-3]
        s2 = verb.get("subj", [None, None])[1] or nous_stem
        subj = [s1 + END_SUBJ[i] if i not in (3, 4) else _imp_stem_fix(s2, END_SUBJ[i]) + END_SUBJ[i] for i in range(6)]
    aux_pres = {"avoir": ["ai", "as", "a", "avons", "avez", "ont"], "être": ["suis", "es", "est", "sommes", "êtes", "sont"]}[aux]
    aux_imp = {"avoir": ["avais", "avais", "avait", "avions", "aviez", "avaient"], "être": ["étais", "étais", "était", "étions", "étiez", "étaient"]}[aux]
    aux_cond = {"avoir": ["aurais", "aurais", "aurait", "aurions", "auriez", "auraient"], "être": ["serais", "serais", "serait", "serions", "seriez", "seraient"]}[aux]

    def plural_pp(i: int) -> str:
        if aux == "être" and i >= 3:
            return pp if pp.endswith(("s", "x")) else pp + "s"
        return pp

    def with_ref(i: int, form: str) -> str:
        return _join(REFLEXIVE[i], form) if pron else form

    table = {
        "pres": [with_ref(i, pres[i]) for i in range(6)],
        "imp": [with_ref(i, _imp_stem_fix(nous_stem, END_IMP[i]) + END_IMP[i]) for i in range(6)],
        "fut": [with_ref(i, fut + END_FUT[i]) for i in range(6)],
        "cond": [with_ref(i, fut + END_IMP[i]) for i in range(6)],
        "subj": [with_ref(i, subj[i]) for i in range(6)],
        "pc": [with_ref(i, f"{aux_pres[i]} {plural_pp(i)}") for i in range(6)],
        "pqp": [with_ref(i, f"{aux_imp[i]} {plural_pp(i)}") for i in range(6)],
        "condp": [with_ref(i, f"{aux_cond[i]} {plural_pp(i)}") for i in range(6)],
    }
    if verb.get("impe"):
        impe = list(verb["impe"])
    else:
        tu = pres[1][:-1] if pres[1].endswith("es") or pres[1] == "vas" else pres[1]
        impe = [tu, pres[3], pres[4]]
        if pron:
            impe = [f"{impe[0]}-toi", f"{impe[1]}-nous", f"{impe[2]}-vous"]
    table["impe"] = impe
    return table


def with_subject(subject: str, form: str, tense: str = "") -> str:
    """«je + aime» → «j'aime»; no subjuntivo, «que + il» → «qu'il»."""
    text = _join(subject, form)
    if tense == "subj":
        text = ("qu'" if subject[:1] in ("i", "e", "o") else "que ") + text
    return text


def accepted_forms(verb: dict, tense: str, person: int, subject: str) -> list[str]:
    """Respostas aceitas para um item de conjugação: a forma, com ou sem o sujeito; concordância com être.

    A primeira da lista é a forma canônica, mostrada como gabarito.
    """
    table = conjugate(verb)
    if tense == "impe":
        return [table["impe"][person]]
    base = table[tense][person]
    forms = [base]
    pron = bool(verb.get("pron"))
    aux = "être" if pron else verb.get("aux", "avoir")
    agree_subject = "il" if subject == "on" else subject
    if tense in ("pc", "pqp", "condp") and aux == "être":
        head = base.rsplit(" ", 1)[0]
        forms = [f"{head} {variant}" for variant in _agree(verb["pp"], person, agree_subject)]
        if subject == "on":
            forms += [f"{head} {v}" for v in _agree(verb["pp"], 3, "nous")]  # «on est partis» = nós
    for alt in (verb.get("alt") or {}).get(tense, [None] * 6)[person:person + 1]:
        if alt:
            forms.append(alt)
    result: list[str] = []
    for form in forms:
        for candidate in (form, with_subject(subject, form), with_subject(subject, form, tense) if tense == "subj" else ""):
            if candidate and candidate not in result:
                result.append(candidate)
    return result


# ============================================================================ conteúdo
class FrenchContent:
    def __init__(self, root: Path):
        self.root = root
        self.units: dict[str, dict] = {}
        self.unit_order: list[str] = []
        self.items: dict[str, dict] = {}     # fr:u:<id> -> item
        self.themes: dict[str, dict] = {}
        self.theme_order: list[str] = []
        self.words: dict[str, dict] = {}     # fr:w:<tema>:<slug> -> palavra
        self.verbs: dict[str, dict] = {}
        self.verb_order: list[str] = []
        self._load()

    def _load(self) -> None:
        for path in sorted((self.root / "units").glob("*.json")):
            for unit in json.loads(path.read_text(encoding="utf-8")).get("units", []):
                unit = {**unit, "item_ids": []}
                for item in unit.get("items", []):
                    item_id = f"fr:u:{item['id']}"
                    self.items[item_id] = {**item, "unit": unit["id"]}
                    unit["item_ids"].append(item_id)
                self.units[unit["id"]] = unit
        self.unit_order = sorted(self.units, key=lambda u: (self.units[u]["phase"], self.units[u]["n"]))
        for path in sorted((self.root / "themes").glob("*.json")):
            for theme in json.loads(path.read_text(encoding="utf-8")).get("themes", []):
                theme = {**theme, "word_ids": []}
                for word in theme.get("words", []):
                    word_id = f"fr:w:{theme['id']}:{slug(word['fr'])}"
                    gender = word.get("g") or ("m" if word["fr"].startswith("le ") else "f" if word["fr"].startswith("la ") else "")
                    pos = word.get("pos") or guess_pos(word["fr"], gender)
                    self.words[word_id] = {**word, "id": word_id, "theme": theme["id"], "g": gender, "pos": pos}
                    theme["word_ids"].append(word_id)
                self.themes[theme["id"]] = theme
        self.theme_order = sorted(self.themes, key=lambda t: self.themes[t]["n"])
        verbs_path = self.root / "verbs.json"
        if verbs_path.exists():
            for verb in json.loads(verbs_path.read_text(encoding="utf-8")).get("verbs", []):
                self.verbs[verb["inf"]] = verb
                self.verb_order.append(verb["inf"])

    def item_kind(self, item_id: str) -> str:
        return item_id.split(":")[1] if item_id.count(":") >= 2 else ""

    def exists(self, item_id: str) -> bool:
        kind = self.item_kind(item_id)
        if kind == "u":
            return item_id in self.items
        if kind == "w":
            return item_id in self.words
        if kind == "v":
            _, _, inf, tense = item_id.split(":", 3)
            return inf in self.verbs and tense in TENSES
        return False

    def category(self, item_id: str) -> str:
        kind = self.item_kind(item_id)
        if kind == "u":
            return self.items[item_id].get("c", "G5")
        if kind == "v":
            return "C"
        return "L2"

    def label(self, item_id: str) -> str:
        kind = self.item_kind(item_id)
        if kind == "u":
            item = self.items[item_id]
            return item.get("q") or (item["a"] if isinstance(item.get("a"), str) else "") or item.get("p", "")
        if kind == "w":
            word = self.words[item_id]
            return f"{word['fr']} · {word['pt']}"
        if kind == "v":
            _, _, inf, tense = item_id.split(":", 3)
            return f"{inf} · {TENSES[tense]}"
        return item_id


# ============================================================================ progresso
class FrenchProgress:
    def __init__(self, path: Path, prefix: str = "fr"):
        self.path = path
        self.p = prefix  # tabelas <prefixo>_items, _attempts, _xp e _meta, no mesmo banco
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self.p}_items (
                    item_id TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT,
                    stage INTEGER NOT NULL DEFAULT 0, best_stage INTEGER NOT NULL DEFAULT 0,
                    due_at TEXT, seen_at TEXT NOT NULL, last_at TEXT, last_success_day TEXT,
                    correct INTEGER NOT NULL DEFAULT 0, assisted INTEGER NOT NULL DEFAULT 0,
                    wrong INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
                    last_score REAL
                );
                CREATE TABLE IF NOT EXISTS {self.p}_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, day TEXT NOT NULL,
                    item_id TEXT NOT NULL, category TEXT, mode TEXT, score REAL, tries INTEGER,
                    answer TEXT, expected TEXT, prompt TEXT
                );
                CREATE TABLE IF NOT EXISTS {self.p}_xp (day TEXT PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS {self.p}_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_{self.p}_items_due ON {self.p}_items(due_at);
                CREATE INDEX IF NOT EXISTS idx_{self.p}_attempts_day ON {self.p}_attempts(day);
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # -- meta (meta diária, recordes, estrelas)
    def meta(self, key: str, default=None):
        with self.connect() as conn:
            row = conn.execute(f"SELECT value FROM {self.p}_meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_meta(self, key: str, value) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO {self.p}_meta VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))

    def states(self) -> dict[str, sqlite3.Row]:
        with self.connect() as conn:
            return {r["item_id"]: r for r in conn.execute(f"SELECT * FROM {self.p}_items")}

    def add_xp(self, amount: int) -> int:
        if amount <= 0:
            return self.xp_today()
        day = today()
        with self._lock, self.connect() as conn:
            conn.execute(f"INSERT INTO {self.p}_xp (day, xp) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET xp = xp + excluded.xp", (day, amount))
            return conn.execute(f"SELECT xp FROM {self.p}_xp WHERE day=?", (day,)).fetchone()["xp"]

    def xp_today(self) -> int:
        with self.connect() as conn:
            row = conn.execute(f"SELECT xp FROM {self.p}_xp WHERE day=?", (today(),)).fetchone()
        return row["xp"] if row else 0

    def mark_seen(self, item_id: str, kind: str, ref: str) -> bool:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO {self.p}_items (item_id, kind, ref, stage, due_at, seen_at) VALUES (?,?,?,0,?,?)",
                (item_id, kind, ref, iso(now_utc() + INTERVALS[0]), iso()),
            )
            return cur.rowcount > 0

    def record(self, item_id: str, kind: str, ref: str, category: str, mode: str, score: float, tries: int,
               answer: str, expected: str, prompt: str) -> dict:
        """Atualiza a revisão espaçada sem punir: o erro recua um estágio, nunca zera o histórico."""
        now = now_utc()
        day = today()
        with self._lock, self.connect() as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO {self.p}_items (item_id, kind, ref, stage, due_at, seen_at) VALUES (?,?,?,0,?,?)",
                (item_id, kind, ref, iso(now), iso(now)),
            )
            row = conn.execute(f"SELECT * FROM {self.p}_items WHERE item_id=?", (item_id,)).fetchone()
            stage, best = row["stage"], row["best_stage"]
            recovered = row["last_score"] is not None and row["last_score"] <= 0 and score > 0
            if score >= 1:
                if row["last_success_day"] != day:
                    # Recuperação: quem já chegou longe volta mais depressa ao ponto em que estava.
                    stage = min(best, stage + 2) if stage + 1 < best else min(stage + 1, len(INTERVALS) - 1)
                due = now + INTERVALS[stage]
                conn.execute(f"UPDATE {self.p}_items SET stage=?, due_at=?, last_at=?, last_success_day=?, correct=correct+1, last_score=? WHERE item_id=?",
                             (stage, iso(due), iso(now), day, score, item_id))
            elif score > 0:
                # Acerto com ajuda: não sobe de estágio e volta antes do que voltaria um acerto direto.
                due = now + (INTERVALS[1] if stage >= 1 else INTERVALS[0])
                conn.execute(f"UPDATE {self.p}_items SET due_at=?, last_at=?, assisted=assisted+1, last_score=? WHERE item_id=?",
                             (iso(due), iso(now), score, item_id))
            else:
                stage = max(0, stage - 1)
                due = now + INTERVALS[0]
                conn.execute(f"UPDATE {self.p}_items SET stage=?, due_at=?, last_at=?, wrong=wrong+1, lapses=lapses+1, last_score=? WHERE item_id=?",
                             (stage, iso(due), iso(now), score, item_id))
            best = max(best, stage)
            conn.execute(f"UPDATE {self.p}_items SET best_stage=? WHERE item_id=?", (best, item_id))
            conn.execute(
                f"INSERT INTO {self.p}_attempts (at, day, item_id, category, mode, score, tries, answer, expected, prompt) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (iso(now), day, item_id, category, mode, score, tries, answer[:2000], expected[:2000], prompt[:500]),
            )
        return {"stage": stage, "best": best, "due_at": iso(due), "mastered": stage >= MASTERED_STAGE, "recovered": recovered}

    def streak(self) -> int:
        goal = self.meta("daily_goal", 150)
        with self.connect() as conn:
            days = {r["day"]: r["xp"] for r in conn.execute(f"SELECT day, xp FROM {self.p}_xp ORDER BY day DESC LIMIT 800")}
        count, day = 0, now_utc().astimezone().date()
        if days.get(day.isoformat(), 0) < max(1, goal // 3):
            day -= timedelta(days=1)  # o dia de hoje ainda pode entrar
        while days.get(day.isoformat(), 0) >= max(1, goal // 3):
            count += 1
            day -= timedelta(days=1)
        return count

    def profile(self) -> dict:
        with self.connect() as conn:
            total = conn.execute(f"SELECT COALESCE(SUM(xp), 0) FROM {self.p}_xp").fetchone()[0]
            week = [dict(r) for r in conn.execute(f"SELECT day, xp FROM {self.p}_xp ORDER BY day DESC LIMIT 7")]
            seen = conn.execute(f"SELECT COUNT(*) FROM {self.p}_items").fetchone()[0]
            mastered = conn.execute(f"SELECT COUNT(*) FROM {self.p}_items WHERE stage >= ?", (MASTERED_STAGE,)).fetchone()[0]
            due = conn.execute(f"SELECT COUNT(*) FROM {self.p}_items WHERE due_at <= ?", (iso(),)).fetchone()[0]
            recovered = conn.execute(
                f"SELECT COUNT(DISTINCT item_id) FROM {self.p}_items WHERE lapses > 0 AND last_score >= 1").fetchone()[0]
        return {"xp_total": total, "xp_today": self.xp_today(), "goal": self.meta("daily_goal", 150),
                "streak": self.streak(), "week": week, "seen": seen, "mastered": mastered, "due": due,
                "recovered": recovered, **level_info(int(total))}

    def challenge_rate(self, item_ids: list[str], hours: int = 3) -> float:
        """Taxa de acerto de primeira no desafio recém-feito, calculada pelas respostas gravadas."""
        if not item_ids:
            return 0.0
        since = iso(now_utc() - timedelta(hours=hours))
        marks = ",".join("?" * len(item_ids))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT item_id, score FROM {self.p}_attempts WHERE mode = 'challenge' AND at >= ? AND item_id IN ({marks}) ORDER BY id",
                (since, *item_ids)).fetchall()
        last = {r["item_id"]: r["score"] for r in rows}  # a tentativa mais recente de cada item
        return sum(1 for i in item_ids if last.get(i, 0) >= 1) / len(item_ids)

    def sprint_score(self, started: str) -> int:
        """Formas certas desde o início do último sprint (limitado aos 100 s do relógio)."""
        if not started:
            return 0
        until = iso(datetime.fromisoformat(started) + timedelta(seconds=100))
        with self.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {self.p}_attempts WHERE mode = 'sprint' AND score >= 1 AND at >= ? AND at <= ?",
                                (started, until)).fetchone()[0]

    def notebook(self, days: int = 30) -> dict:
        since = (now_utc().astimezone().date() - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT category, COUNT(*) AS n, SUM(CASE WHEN score >= 1 THEN 1 ELSE 0 END) AS ok FROM {self.p}_attempts "
                "WHERE day >= ? GROUP BY category", (since,)).fetchall()
            recent = [dict(r) for r in conn.execute(
                f"SELECT at, item_id, category, answer, expected, prompt, tries FROM {self.p}_attempts "
                "WHERE day >= ? AND score < 1 ORDER BY id DESC LIMIT 40", (since,))]
            open_items = [r["item_id"] for r in conn.execute(
                f"SELECT DISTINCT a.item_id FROM {self.p}_attempts a JOIN {self.p}_items i ON i.item_id = a.item_id "
                "WHERE a.day >= ? AND a.score < 1 AND (i.last_score IS NULL OR i.last_score < 1)", (since,))]
        stats = {r["category"]: {"attempts": r["n"], "ok": r["ok"] or 0} for r in rows}
        return {"stats": stats, "recent": recent, "open_items": open_items}


# ============================================================================ motor
class FrenchCourse:
    MAX_TRIES = {"mc": 2, "register": 2, "gender": 2, "fr_pt": 2, "pt_fr": 2, "listen": 2,
                 "gap": 3, "type": 3, "transform": 3, "order": 3, "fix": 3, "dict": 2, "pairs": 1, "conj": 1}

    def __init__(self, root: Path, db_path: Path):
        self.content = FrenchContent(root)
        self.progress = FrenchProgress(db_path)
        self.pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    # -- tokens
    def _token(self, payload: dict) -> str:
        token = secrets.token_urlsafe(9)
        with self._lock:
            if len(self.pending) > 20000:
                self.pending.clear()
            self.pending[token] = {**payload, "tries": 0, "picks": 0}
        return token

    # -- visão geral
    def overview(self) -> dict:
        states = self.progress.states()
        now = iso()
        stars = self.progress.meta("unit_stars", {})

        def tally(ids: list[str]) -> dict:
            seen = mastered = due = 0
            for item_id in ids:
                state = states.get(item_id)
                if not state:
                    continue
                seen += 1
                mastered += state["stage"] >= MASTERED_STAGE
                due += bool(state["due_at"] and state["due_at"] <= now)
            return {"total": len(ids), "seen": seen, "mastered": mastered, "due": due}

        phases = []
        for phase in PHASES:
            units = []
            for unit_id in self.content.unit_order:
                unit = self.content.units[unit_id]
                if unit["phase"] != phase["n"]:
                    continue
                units.append({"id": unit_id, "n": unit["n"], "title": unit["title"], "prio": unit.get("prio", 2),
                              "theme": unit.get("theme", ""), "goal": unit.get("goal", ""), "stars": stars.get(unit_id, 0),
                              "extra": bool(unit.get("extra")), **tally(unit["item_ids"])})
            phases.append({**phase, "units": units})
        themes = []
        for theme_id in self.content.theme_order:
            theme = self.content.themes[theme_id]
            themes.append({"id": theme_id, "n": theme["n"], "name": theme["name"], "fr": theme["fr"],
                           "color": theme.get("color", "#2d4fa3"), "desc": theme.get("desc", ""),
                           "delf": bool(theme.get("delf")), "units": theme.get("units", []),
                           "preview": [self.content.words[w]["fr"] for w in theme["word_ids"][:4]], **tally(theme["word_ids"])})
        verbs = []
        for inf in self.content.verb_order:
            verb = self.content.verbs[inf]
            ids = [f"fr:v:{inf}:{t}" for t in TENSES]
            row = tally(ids)
            verbs.append({"inf": inf, "pt": verb.get("pt", ""), "family": verb.get("family", ""),
                          "tenses": {t: (states[f"fr:v:{inf}:{t}"]["stage"] if f"fr:v:{inf}:{t}" in states else None) for t in TENSES},
                          **row})
        profile = self.progress.profile()
        notebook = self.progress.notebook()
        return {"phases": phases, "themes": themes, "verbs": verbs, "tenses": TENSES, "categories": CATEGORIES,
                "profile": profile, "notebook": {"stats": notebook["stats"], "open": len(notebook["open_items"])},
                "achievements": self.achievements(profile, states, stars), "sprint_best": self.progress.meta("sprint_best", 0)}

    def achievements(self, profile: dict, states: dict, stars: dict) -> list[dict]:
        units_done = sum(1 for u in self.content.units.values()
                         if u["item_ids"] and all(i in states for i in u["item_ids"]))
        three = sum(1 for v in stars.values() if v >= 3)
        verbs_mastered = sum(1 for inf in self.content.verbs
                             if all(states.get(f"fr:v:{inf}:{t}") and states[f"fr:v:{inf}:{t}"]["stage"] >= 2 for t in ("pres", "pc", "imp", "fut", "subj")))
        sprint = self.progress.meta("sprint_best", 0)
        defs = [
            ("premier-pas", "Premier pas", "Concluir a primeira unidade da trilha.", units_done >= 1),
            ("phase-1", "Fondations", "Ver todos os itens da fase 1.", self._phase_seen(1, states)),
            ("phase-2", "Argumentateur", "Ver todos os itens da fase 2.", self._phase_seen(2, states)),
            ("phase-3", "Styliste", "Ver todos os itens da fase 3.", self._phase_seen(3, states)),
            ("etoiles", "Trois étoiles", "Tirar três estrelas no desafio de uma unidade.", three >= 1),
            ("constellation", "Constellation", "Três estrelas em dez unidades.", three >= 10),
            ("sprint-20", "Sprinter", "Acertar 20 formas num sprint de verbos.", sprint >= 20),
            ("sprint-40", "Mitraillette", "Acertar 40 formas num sprint de verbos.", sprint >= 40),
            ("verbes-10", "Conjugueur", "Dominar 5 tempos de 10 verbos.", verbs_mastered >= 10),
            ("rattrapage", "Rattrapage", "Recuperar 25 itens que você tinha errado.", profile["recovered"] >= 25),
            ("semaine", "Une semaine", "Sete dias seguidos cumprindo ao menos 1/3 da meta.", profile["streak"] >= 7),
            ("mois", "Un mois", "Trinta dias seguidos.", profile["streak"] >= 30),
            ("cent", "Cent", "Dominar 100 itens.", profile["mastered"] >= 100),
            ("mille", "Mille", "Dominar 1.000 itens.", profile["mastered"] >= 1000),
        ]
        return [{"id": i, "title": t, "desc": d, "done": bool(ok)} for i, t, d, ok in defs]

    def _phase_seen(self, phase: int, states: dict) -> bool:
        ids = [i for u in self.content.units.values() if u["phase"] == phase for i in u["item_ids"]]
        return bool(ids) and all(i in states for i in ids)

    # -- telas
    def rule_screen(self, unit: dict) -> dict:
        return {"type": "rule", "unit_id": unit["id"], "title": unit["title"], "n": unit["n"], "goal": unit.get("goal", ""),
                "rules": unit.get("rules", []), "kind": "rule"}

    def unit_exercise(self, item_id: str, mode: str = "") -> dict:
        item = self.content.items[item_id]
        t = item["t"]
        base = {"item_id": item_id, "kind": "u", "t": t, "category": item.get("c", "G5"),
                "category_label": CATEGORIES.get(item.get("c", "G5"), ""), "unit_id": item["unit"],
                "unit_title": self.content.units[item["unit"]]["title"], "q": item.get("q", ""), "p": item.get("p", "")}
        pend = {"item_id": item_id, "kind": "u", "ref": item["unit"], "category": item.get("c", "G5"), "t": t,
                "e": item.get("e", ""), "h": item.get("h", ""), "prompt": item.get("q", "") or item.get("p", ""), "full": item.get("full", ""),
                "pt": item.get("pt", "")}
        if t == "mc":
            options = shuffled([item["a"]] + list(item["w"]))
            base.update(options=options)
            pend.update(accept=[item["a"]], answer=item["a"])
        elif t == "register":
            options = list(REGISTERS.values())
            base.update(options=options)
            pend.update(accept=[REGISTERS[item["a"]]], answer=REGISTERS[item["a"]])
        elif t == "gap":
            accept = item["a"] if isinstance(item["a"], list) else [item["a"]]
            base.update(blanks=item["q"].count("___"))
            pend.update(accept=accept, answer=accept[0], typed=True)
        elif t == "transform":
            accept = item["a"] if isinstance(item["a"], list) else [item["a"]]
            base.update(start=item.get("start", ""))
            pend.update(accept=accept, answer=accept[0], typed=True)
        elif t == "fix":
            tokens = item["q"].split()
            bad = item["bad"].split()
            start = next(i for i in range(len(tokens)) if [strip_punct(x) for x in tokens[i:i + len(bad)]] == [strip_punct(b) for b in bad])
            accept = item["a"] if isinstance(item["a"], list) else [item["a"]]
            base.update(tokens=tokens)
            pend.update(accept=accept, answer=accept[0], typed=True, bad=list(range(start, start + len(bad))),
                        full=item.get("full", ""))
        elif t == "order":
            words = item["a"].split()
            tokens = words + list(item.get("x", []))
            mixed = shuffled(tokens)
            while len(mixed) > 2 and mixed[:len(words)] == words:
                mixed = shuffled(tokens)
            base.update(tokens=mixed)
            pend.update(accept=[item["a"]] + list(item.get("alt", [])), answer=item["a"], first=words[0])
        elif t == "pairs":
            pairs = item["p"]
            base.update(left=shuffled([p[0] for p in pairs]), right=shuffled([p[1] for p in pairs]))
            pend.update(pairs=[list(p) for p in pairs], answer="; ".join(f"{a} → {b}" for a, b in pairs))
        elif t == "dict":
            base.update(audio=item["a"])
            pend.update(answer=item["a"], accept=[item["a"]], typed=True, dictation=True)
        else:
            raise ValueError(f"Tipo desconhecido: {t}")
        base["max_tries"] = self.MAX_TRIES.get(t, 2)
        base["token"] = self._token(pend)
        return base

    def word_intro(self, word_id: str) -> dict:
        word = self.content.words[word_id]
        return {"type": "word", "kind": "w", "item_id": word_id, "word": {k: word.get(k, "") for k in ("fr", "pt", "lv", "ex", "ex_pt", "n", "g", "pos", "reg")},
                "theme": self.content.themes[word["theme"]]["name"]}

    def word_exercise(self, word_id: str, variant: str) -> dict | None:
        word = self.content.words[word_id]
        theme = self.content.themes[word["theme"]]
        pool = [self.content.words[w] for w in theme["word_ids"] if w != word_id]
        same_pos = [w for w in pool if w["pos"] == word["pos"]] or pool
        base = {"item_id": word_id, "kind": "w", "category": "L2", "category_label": CATEGORIES["L2"], "theme_name": theme["name"]}
        pend = {"item_id": word_id, "kind": "w", "ref": word["theme"], "category": "L2", "e": word.get("n", ""),
                "pt": word.get("ex_pt", ""), "full": f"{word['fr']} = {word['pt']}", "prompt": word["fr"]}
        if variant == "gender":
            if word["pos"] != "noun" or not word["g"] or word["fr"].startswith("les "):
                variant = "pt_fr"
            else:
                bare = re.sub(r"^(le |la |l')", "", word["fr"])
                options = ["le (masculino)", "la (feminino)"]
                answer = options[0] if word["g"] == "m" else options[1]
                pend.update(accept=[answer], answer=answer, category="G4", prompt=bare)
                base.update(t="gender", q=bare, options=options, category="G4", category_label=CATEGORIES["G4"],
                            instruction="Masculino ou feminino?", hint=word["pt"])
        if variant == "gap":
            head = re.sub(r"^(le |la |les |l'|se |s')", "", word["fr"])
            sentence = word.get("ex", "")
            match = re.search(rf"(?<![\wÀ-ÿ]){re.escape(head)}(?![\wÀ-ÿ])", sentence, re.I) if head and sentence else None
            if not match:
                variant = "type"
            else:
                gapped = sentence[:match.start()] + "___" + sentence[match.end():]
                pend.update(accept=[match.group(0)], answer=match.group(0), typed=True, prompt=sentence)
                base.update(t="gap", q=gapped, p=word.get("ex_pt", ""), instruction="Complete com a palavra do tema.", hint=word["pt"])
        if variant == "type":
            accept = [word["fr"]] + list(word.get("alt", []))
            pend.update(accept=accept, answer=word["fr"], typed=True, need_article=word["pos"] == "noun",
                        prompt=word["pt"])
            base.update(t="type", q=word["pt"], instruction="Escreva em francês" + (" com o artigo." if word["pos"] == "noun" else "."),
                        hint=word.get("lv", ""))
        if variant in ("fr_pt", "listen"):
            others = random.sample(same_pos, min(3, len(same_pos)))
            options = shuffled([word["pt"]] + [o["pt"] for o in others])
            pend.update(accept=[word["pt"]], answer=word["pt"])
            base.update(t=variant, q="" if variant == "listen" else word["fr"], options=options, audio=word["fr"],
                        instruction="Ouça e escolha o sentido." if variant == "listen" else "O que significa?")
        if variant == "pt_fr":
            others = random.sample(same_pos, min(3, len(same_pos)))
            options = shuffled([word["fr"]] + [o["fr"] for o in others])
            pend.update(accept=[word["fr"]], answer=word["fr"], prompt=word["pt"])
            base.update(t="pt_fr", q=word["pt"], options=options, instruction="Como se diz em francês?")
        base["max_tries"] = self.MAX_TRIES.get(base["t"], 2)
        pend["t"] = base["t"]
        base["token"] = self._token(pend)
        base["audio_after"] = word["fr"]
        return base

    def verb_question(self, inf: str, tense: str) -> dict:
        verb = self.content.verbs[inf]
        if tense == "impe" and (verb.get("no_impe") or verb.get("impersonal")):
            tense = "pres"
        persons = [2] if verb.get("impersonal") else [0, 1, 3, 4] if tense == "impe" else list(range(6))
        person = random.choice(persons)
        if tense == "impe":
            index = {0: 0, 1: 0, 3: 1, 4: 2}[person]
            subject = ["(tu)", "(nous)", "(vous)"][index]
            accept = accepted_forms(verb, tense, index, subject)
            shown = subject
        else:
            subject = PRONOUNS[person]
            if person == 2 and not verb.get("impersonal"):
                subject = random.choice(["il", "elle", "on"])
            if person == 5:
                subject = random.choice(["ils", "elles"])
            accept = accepted_forms(verb, tense, person, subject)
            shown = subject
        token = self._token({"item_id": f"fr:v:{inf}:{tense}", "kind": "v", "ref": inf, "category": "C", "accept": accept,
                             "answer": accept[0], "typed": True, "e": verb.get("note", ""), "prompt": f"{shown} · {inf} · {TENSES[tense]}",
                             "conj": True})
        return {"t": "conj", "kind": "v", "item_id": f"fr:v:{inf}:{tense}", "inf": inf, "pt": verb.get("pt", ""),
                "tense": tense, "tense_label": TENSES[tense], "subject": shown, "token": token, "max_tries": 1,
                "category": "C", "category_label": CATEGORIES["C"]}

    # -- sessões
    def _order_items(self, ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda i: (TYPE_ORDER.get(self.content.items[i]["t"], 9), self.content.items[i]["id"]))

    def unit_session(self, unit_id: str, mode: str) -> dict:
        unit = self.content.units.get(unit_id)
        if not unit:
            raise ValueError("Unidade desconhecida.")
        states = self.progress.states()
        steps: list[dict] = []
        if mode == "challenge":
            ids = shuffled(unit["item_ids"])
            steps = [self.unit_exercise(i, "challenge") for i in ids]
            return {"mode": "challenge", "title": f"Desafio · {unit['n']}. {unit['title']}", "unit_id": unit_id, "steps": steps}
        new = [i for i in unit["item_ids"] if i not in states]
        seen = [i for i in unit["item_ids"] if i in states]
        steps.append(self.rule_screen(unit))
        chosen = self._order_items(new) if new else self._order_items(random.sample(seen, min(10, len(seen))))
        steps += [self.unit_exercise(i) for i in chosen]
        recap = [i for i in seen if i not in chosen]
        random.shuffle(recap)
        steps += [self.unit_exercise(i) for i in recap[:3]]
        return {"mode": "learn", "title": f"{unit['n']}. {unit['title']}", "unit_id": unit_id, "steps": steps}

    def theme_session(self, theme_id: str, size: int = 8) -> dict:
        theme = self.content.themes.get(theme_id)
        if not theme:
            raise ValueError("Eixo desconhecido.")
        states = self.progress.states()
        new = [w for w in theme["word_ids"] if w not in states][:size]
        steps: list[dict] = []
        for start in range(0, len(new), 4):
            chunk = new[start:start + 4]
            steps += [self.word_intro(w) for w in chunk]
            first = [self.word_exercise(w, "fr_pt") for w in chunk]
            second = [self.word_exercise(w, random.choice(["pt_fr", "gender", "listen"])) for w in chunk]
            random.shuffle(first)
            random.shuffle(second)
            steps += first + second
        harder = [self.word_exercise(w, random.choice(["type", "gap"])) for w in new]
        random.shuffle(harder)
        steps += harder
        if not new:
            seen = [w for w in theme["word_ids"] if w in states]
            steps = [self.word_exercise(w, random.choice(["type", "gap", "pt_fr"])) for w in random.sample(seen, min(12, len(seen)))]
        return {"mode": "theme", "title": f"{theme['fr']} · {theme['name']}", "theme_id": theme_id, "steps": [s for s in steps if s]}

    def review_session(self, scope: str = "", size: int = 20) -> dict:
        states = self.progress.states()
        now = iso()
        pool = [s for s in states.values() if self.content.exists(s["item_id"])]
        if scope.startswith("unit:"):
            pool = [s for s in pool if s["kind"] == "u" and self.content.items[s["item_id"]]["unit"] == scope[5:]]
        elif scope.startswith("theme:"):
            pool = [s for s in pool if s["kind"] == "w" and self.content.words[s["item_id"]]["theme"] == scope[6:]]
        due = sorted([s for s in pool if s["due_at"] and s["due_at"] <= now], key=lambda s: s["due_at"])
        chosen = due[:size]
        if len(chosen) < size and (scope or not chosen):
            taken = {s["item_id"] for s in chosen}
            rest = sorted([s for s in pool if s["item_id"] not in taken], key=lambda s: (s["stage"], -s["lapses"], s["last_at"] or ""))
            chosen += rest[: size - len(chosen)]
        steps = [self._review_step(s) for s in chosen]
        random.shuffle(steps)
        return {"mode": "review", "title": "Revisão", "steps": [s for s in steps if s], "due": len(due)}

    def _review_step(self, state: sqlite3.Row) -> dict | None:
        item_id, stage = state["item_id"], state["stage"]
        kind = state["kind"]
        if kind == "u":
            return self.unit_exercise(item_id, "review")
        if kind == "w":
            variants = ["fr_pt", "pt_fr", "gender"] if stage <= 1 else ["pt_fr", "gap", "listen"] if stage <= 3 else ["type", "gap"]
            return self.word_exercise(item_id, random.choice(variants))
        if kind == "v":
            _, _, inf, tense = item_id.split(":", 3)
            return self.verb_question(inf, tense)
        return None

    def notebook_session(self, category: str = "") -> dict:
        data = self.progress.notebook(60)
        ids = [i for i in data["open_items"] if self.content.exists(i)]
        if category:
            ids = [i for i in ids if self.content.category(i) == category]
        if not ids:
            raise ValueError("O caderno de erros está em dia nesta categoria. Bom trabalho!")
        random.shuffle(ids)
        states = self.progress.states()
        steps = [self._review_step(states[i]) for i in ids[:20] if i in states]
        title = f"Caderno de erros · {CATEGORIES.get(category, 'todas as categorias')}"
        return {"mode": "notebook", "title": title, "steps": [s for s in steps if s]}

    def diagnostic_session(self) -> dict:
        steps = []
        for unit_id in self.content.unit_order:
            unit = self.content.units[unit_id]
            if unit["phase"] > 2 or unit.get("extra") or not unit["item_ids"]:
                continue
            candidates = [i for i in unit["item_ids"] if self.content.items[i]["t"] in ("mc", "gap", "fix")]
            if candidates:
                steps.append(self.unit_exercise(random.choice(candidates), "diagnostic"))
        return {"mode": "diagnostic", "title": "Diagnóstico", "steps": steps}

    def sprint_batch(self, tenses: list[str], verbs: list[str], count: int = 60) -> dict:
        tenses = [t for t in tenses if t in TENSES] or ["pres", "pc", "imp", "fut", "cond", "subj"]
        verbs = [v for v in verbs if v in self.content.verbs] or list(self.content.verb_order)
        steps = [self.verb_question(random.choice(verbs), random.choice(tenses)) for _ in range(count)]
        self.progress.set_meta("sprint_started", iso())  # o placar é contado no servidor a partir daqui
        return {"mode": "sprint", "title": "Sprint de verbos", "steps": steps, "seconds": 90}

    def verb_table(self, inf: str) -> dict:
        verb = self.content.verbs.get(inf)
        if not verb:
            raise ValueError("Verbo desconhecido.")
        table = conjugate(verb)
        rows = {}
        for tense, forms in table.items():
            if tense == "impe":
                if not (verb.get("no_impe") or verb.get("impersonal")):
                    rows[tense] = forms
            else:
                persons = [2] if verb.get("impersonal") else range(6)
                rows[tense] = [with_subject(PRONOUNS[i], forms[i], tense) for i in persons]
        states = self.progress.states()
        return {"inf": inf, "pt": verb.get("pt", ""), "aux": "être" if verb.get("pron") else verb.get("aux", "avoir"),
                "pp": verb["pp"], "family": verb.get("family", ""), "note": verb.get("note", ""), "tenses": TENSES, "table": rows,
                "states": {t: (states[f"fr:v:{inf}:{t}"]["stage"] if f"fr:v:{inf}:{t}" in states else None) for t in TENSES}}

    def again(self, item_id: str) -> dict:
        """Nova versão da mesma pergunta, para voltar algumas telas depois de um erro."""
        if not self.content.exists(item_id):
            raise ValueError("Item desconhecido.")
        kind = self.content.item_kind(item_id)
        if kind == "u":
            return self.unit_exercise(item_id, "again")
        if kind == "w":
            return self.word_exercise(item_id, random.choice(["pt_fr", "fr_pt", "gap"]))
        _, _, inf, tense = item_id.split(":", 3)
        return self.verb_question(inf, tense)

    def theme_detail(self, theme_id: str) -> dict:
        theme = self.content.themes.get(theme_id)
        if not theme:
            raise ValueError("Eixo desconhecido.")
        states = self.progress.states()
        words = []
        for word_id in theme["word_ids"]:
            word = self.content.words[word_id]
            state = states.get(word_id)
            words.append({"id": word_id, "fr": word["fr"], "pt": word["pt"], "lv": word.get("lv", ""), "reg": word.get("reg", ""),
                          "stage": state["stage"] if state else None})
        return {"id": theme_id, "name": theme["name"], "fr": theme["fr"], "desc": theme.get("desc", ""),
                "color": theme.get("color", ""), "units": theme.get("units", []), "words": words}

    def notebook(self) -> dict:
        data = self.progress.notebook()
        recent = []
        for row in data["recent"]:
            item_id = row["item_id"]
            if not self.content.exists(item_id):
                continue
            recent.append({**row, "label": self.content.label(item_id), "category_label": CATEGORIES.get(row["category"] or "", "")})
        return {"stats": data["stats"], "recent": recent, "open": len(data["open_items"]), "categories": CATEGORIES}

    def unit_detail(self, unit_id: str) -> dict:
        unit = self.content.units.get(unit_id)
        if not unit:
            raise ValueError("Unidade desconhecida.")
        return {k: unit.get(k) for k in ("id", "n", "phase", "title", "goal", "rules", "theme", "prio", "sources")}

    def mark_seen(self, item_id: str) -> dict:
        if not self.content.exists(item_id):
            raise ValueError("Item desconhecido.")
        kind = self.content.item_kind(item_id)
        ref = self.content.words[item_id]["theme"] if kind == "w" else ""
        fresh = self.progress.mark_seen(item_id, kind, ref)
        xp = self.progress.add_xp(XP_INTRO if fresh else 0)
        return {"ok": True, "xp": XP_INTRO if fresh else 0, "xp_today": xp}

    def finish(self, payload: dict) -> dict:
        """Fim de sessão: estrelas do desafio e recorde do sprint."""
        mode = payload.get("mode")
        result: dict = {}
        if mode == "challenge":
            unit_id = str(payload.get("unit_id", ""))
            if unit_id in self.content.units:
                rate = self.progress.challenge_rate(self.content.units[unit_id]["item_ids"])
                got = 3 if rate >= 0.95 else 2 if rate >= 0.8 else 1 if rate >= 0.6 else 0
                stars = self.progress.meta("unit_stars", {})
                result["stars"] = got
                result["best_stars"] = max(got, stars.get(unit_id, 0))
                result["new_best"] = got > stars.get(unit_id, 0)
                if got > stars.get(unit_id, 0):
                    stars[unit_id] = got
                    self.progress.set_meta("unit_stars", stars)
        if mode == "sprint":
            score = self.progress.sprint_score(self.progress.meta("sprint_started", ""))
            best = self.progress.meta("sprint_best", 0)
            result["score"] = score
            result["record"] = score > best
            result["best"] = max(score, best)
            if score > best:
                self.progress.set_meta("sprint_best", score)
        result["profile"] = self.progress.profile()
        return result

    def set_goal(self, goal: int) -> dict:
        if goal not in (50, 100, 150, 250, 400):
            raise ValueError("Meta inválida.")
        self.progress.set_meta("daily_goal", goal)
        return self.progress.profile()

    # -- correção
    def answer(self, payload: dict) -> dict:
        token = str(payload.get("token", ""))
        with self._lock:
            pend = self.pending.get(token)
        if not pend:
            raise ValueError("Esta pergunta expirou. Feche a sessão e comece outra.")
        t = pend.get("t", "")
        mode = str(payload.get("mode", ""))
        # Fase 1 do "caça ao erro": localizar a palavra errada.
        if "pick" in payload and pend.get("bad") is not None and pend.get("located"):
            return {"located": True, "final": False, "bad": pend["bad"]}
        if "pick" in payload and pend.get("bad") is not None and not pend.get("located"):
            pick = int(payload.get("pick", -1))
            if pick in pend["bad"]:
                pend["located"] = True
                return {"located": True, "final": False, "bad": pend["bad"]}
            pend["picks"] += 1
            if pend["picks"] >= 2:
                pend["located"] = True
                return {"located": False, "final": False, "bad": pend["bad"], "hint": "O erro está aqui. Agora corrija."}
            return {"located": False, "final": False, "hint": "O erro está em outra parte da frase. Leia de novo."}
        given = payload.get("answer", "")
        if not isinstance(given, list) and not norm(given) and "pairs" not in pend:
            return {"final": False, "correct": False, "try": pend["tries"], "hint": "Escreva uma resposta (vale tentar).", "verdict": "empty"}
        pend["tries"] += 1
        tries = pend["tries"]
        max_tries = self.MAX_TRIES.get(t, self.MAX_TRIES.get(pend.get("kind_t", ""), 2))
        if pend.get("conj"):
            max_tries = 1
        extra: dict = {}
        if "pairs" in pend:
            score, marks = grade_pairs(pend["pairs"], given if isinstance(given, list) else [])
            correct, final = score >= 1, True
            extra["marks"] = marks
            given_text = "; ".join(f"{p.get('left')} → {p.get('right')}" for p in given if isinstance(p, dict)) if isinstance(given, list) else ""
            return self._finalize(token, pend, score, given_text, mode, extra, correct)
        given_text = str(given)
        verdict, note = self._check(pend, given_text)
        if pend.get("dictation"):
            ratio, words = dictation_marks(given_text, pend["answer"])
            extra["words"] = words
            if verdict != "ok" and ratio >= 0.999:
                verdict = "accent"
        if verdict == "ok":
            score = SCORE_BY_TRY.get(tries, 0.4) if pend.get("picks", 0) == 0 else min(SCORE_BY_TRY.get(tries, 0.4), 0.7)
            return self._finalize(token, pend, score, given_text, mode, extra, True)
        if tries < max_tries:
            hint = self._hint(pend, tries, verdict, note)
            return {"final": False, "correct": False, "try": tries, "hint": hint, "verdict": verdict, **extra}
        return self._finalize(token, pend, 0.0, given_text, mode, extra, False)

    def _check(self, pend: dict, given: str) -> tuple[str, str]:
        answer = norm(given)
        if not answer:
            return "empty", ""
        accept = [norm(a) for a in pend.get("accept", []) if a]
        if answer in accept:
            return "ok", ""
        bare = strip_accents(answer)
        if any(bare == strip_accents(a) for a in accept):
            return "accent", ""
        if pend.get("need_article"):
            noun = re.sub(r"^(le |la |les |l'|un |une )", "", answer)
            if any(noun == re.sub(r"^(le |la |les |l')", "", a) for a in accept):
                return "article", ""
            if any(strip_accents(noun) == strip_accents(re.sub(r"^(le |la |les |l')", "", a)) for a in accept):
                return "article", ""
        if pend.get("typed"):
            best = max((difflib.SequenceMatcher(None, bare, strip_accents(a)).ratio() for a in accept), default=0)
            if best >= 0.88:
                return "close", ""
        return "wrong", ""

    def _hint(self, pend: dict, tries: int, verdict: str, note: str) -> str:
        if verdict == "accent":
            return "Quase! Só faltou acertar os acentos (é, è, à, ç…). Tente de novo."
        if verdict == "article":
            return "A palavra está certa; confira o artigo (gênero ou elisão)."
        if verdict == "empty":
            return "Escreva uma resposta (vale tentar)."
        if pend.get("t") == "order":
            return "A ordem ainda não está certa." if tries == 1 else f"Dica: a frase começa por «{pend.get('first', '')}»."
        if tries == 1:
            signal = SIGNALS.get(pend.get("category", ""), "Quase. Releia com calma.")
            if verdict == "close":
                return "Está muito perto: confira letra por letra. " + signal.replace("Quase. ", "")
            return signal
        return pend.get("h") or first_sentence(pend.get("e", "")) or "Pense na regra da unidade."

    def _finalize(self, token: str, pend: dict, score: float, given: str, mode: str, extra: dict, correct: bool) -> dict:
        with self._lock:
            self.pending.pop(token, None)
        tries = pend["tries"]
        state = self.progress.record(pend["item_id"], pend["kind"], pend.get("ref", ""), pend.get("category", ""), mode, score,
                                     tries, given, str(pend.get("answer", "")), str(pend.get("prompt", "")))
        if score >= 1:
            xp = XP_BY_TRY[1]
        elif score >= 0.7:
            xp = XP_BY_TRY[2]
        elif score > 0:
            xp = XP_BY_TRY[3]
        else:
            xp = XP_FAIL
        bonus = XP_RECOVERY if state["recovered"] else 0
        xp_today = self.progress.add_xp(xp + bonus)
        return {
            "final": True, "correct": correct, "score": score, "try": tries, "answer": pend.get("answer", ""),
            "explanation": pend.get("e", ""), "full": pend.get("full", ""), "translation": pend.get("pt", ""),
            "xp": xp, "bonus": bonus, "recovered": state["recovered"], "xp_today": xp_today, "state": state, **extra,
        }


def guess_pos(fr: str, gender: str) -> str:
    if gender or fr.startswith(("le ", "la ", "les ", "l'")):
        return "noun"
    core = re.sub(r"^(se |s')", "", fr)
    if " " not in core and re.search(r"(er|ir|re|oir)$", core):
        return "verb"
    return "other"


def first_sentence(text: str) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", text or "")
    return match.group(1) if match else (text or "")


def strip_punct(token: str) -> str:
    return norm(re.sub(r"^[«\"(]+|[»\",.;:!?)]+$", "", token))


def grade_pairs(pairs: list[list[str]], given: list) -> tuple[float, list[dict]]:
    expected = {norm(a): b for a, b in pairs}
    marks = []
    hits = 0
    for entry in given:
        if not isinstance(entry, dict):
            continue
        left, right = str(entry.get("left", "")), str(entry.get("right", ""))
        ok = norm(expected.get(norm(left), "")) == norm(right)
        hits += ok
        marks.append({"left": left, "right": right, "ok": ok, "expected": expected.get(norm(left), "")})
    return (round(hits / len(pairs), 2) if pairs else 0.0), marks


def dictation_marks(given: str, expected: str) -> tuple[float, list[dict]]:
    target_words = WORD_RE.findall(expected)
    target = [norm(w) for w in target_words]
    typed = [norm(w) for w in WORD_RE.findall(given)]
    matcher = difflib.SequenceMatcher(None, [strip_accents(w) for w in typed], [strip_accents(w) for w in target], autojunk=False)
    hits: set[int] = set()
    for block in matcher.get_matching_blocks():
        hits.update(range(block.b, block.b + block.size))
    words = [{"w": w, "ok": i in hits} for i, w in enumerate(target_words)]
    return (len(hits) / len(target) if target else 0.0), words
