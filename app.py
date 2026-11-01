#!/usr/bin/env python3
"""LinguaLab Russo: curso temático de vocabulário e gramática, nível intermediário e avançado.

O vocabulário inteiro do OpenRussian fica em data/lexicon.sqlite3.gz (ver tools/build_lexicon.py),
classificado por eixos temáticos não excludentes e ordenado por utilidade. Os exercícios de
gramática e as construções das versões anteriores são redistribuídos pelos mesmos temas.
O progresso do aluno fica em <pasta de dados>/data/lingualab.sqlite3.
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import os
import random
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import edge_tts
    import edge_tts.communicate as edge_communicate
    from edge_tts.constants import TRUSTED_CLIENT_TOKEN as EDGE_TOKEN
except ImportError:  # o app continua funcionando sem áudio
    edge_tts = None

# Em 10/10/2026 a Microsoft passou a recusar (403) o endereço antigo do edge-tts 7.2.8; o Edge
# atual fala com api.msedgeservices.com (edge-tts issue #490). Tentamos o novo primeiro.
EDGE_ENDPOINTS = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key={token}",
    "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken={token}",
)

from lessons import LessonStore, grade_cloze, grade_match
from updater import Updater, UpdateError

APP_VERSION = "1.6.3"
FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)


def _early_arg(name: str) -> str:
    """Lê um argumento antes do argparse: os caminhos abaixo são resolvidos já na importação."""
    if name in sys.argv[:-1]:
        return sys.argv[sys.argv.index(name) + 1]
    return ""


if _early_arg("--data-dir"):
    os.environ["RUSSO_USER_DIR"] = _early_arg("--data-dir")
if os.environ.get("RUSSO_USER_DIR"):
    # Pasta de dados alternativa: permite rodar uma versão de teste sem tocar no progresso real.
    USER_DIR = Path(os.environ["RUSSO_USER_DIR"])
else:
    USER_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "RussoTrainer" if FROZEN else BASE_DIR
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
LEXICON_GZ = DATA_DIR / "lexicon.sqlite3.gz"
THEMES_PATH = DATA_DIR / "themes.json"
UNITS_DIR = DATA_DIR / "units"
VOCAB_DIR = DATA_DIR / "vocab_lessons"
PREFIX_PATH = DATA_DIR / "prefix_verbs.json"
LESSONS_DIR = DATA_DIR / "lessons"
CACHE_DIR = USER_DIR / "data" / "cache"
DB_PATH = Path(os.environ.get("RUSSO_DB_PATH", str(USER_DIR / "data" / "lingualab.sqlite3")))
TTS_CACHE_DIR = USER_DIR / "data" / "tts_cache"

LEVELS = ["A2", "B1", "B2", "C1", "C2"]
ASPECTS = [
    {"id": "verbos", "label": "Verbos", "kind": "word", "pos": "verb"},
    {"id": "substantivos", "label": "Substantivos", "kind": "word", "pos": "noun"},
    {"id": "adjetivos", "label": "Adjetivos", "kind": "word", "pos": "adjective"},
    {"id": "outros", "label": "Advérbios e outras palavras", "kind": "word", "pos": "other"},
    {"id": "estruturas", "label": "Estruturas gramaticais", "kind": "structure"},
    {"id": "expressoes", "label": "Expressões e construções", "kind": "expression"},
    {"id": "leitura", "label": "Leitura", "kind": "lesson"},
    {"id": "escuta", "label": "Compreensão oral", "kind": "lesson"},
    {"id": "producao", "label": "Produção escrita e oral", "kind": "lesson"},
]
POS_ASPECT = {a["pos"]: a["id"] for a in ASPECTS if a["kind"] == "word"}
POS_LABEL = {"noun": "substantivo", "verb": "verbo", "adjective": "adjetivo", "other": "advérbio / outra classe"}
GENDER_LABEL = {"m": "masculino", "f": "feminino", "n": "neutro", "pl": "só plural"}
# Revisão espaçada: estágio -> intervalo até a próxima revisão.
INTERVALS = [timedelta(minutes=10), timedelta(days=1), timedelta(days=3), timedelta(days=7),
             timedelta(days=14), timedelta(days=30), timedelta(days=60), timedelta(days=120), timedelta(days=240)]
MASTERED_STAGE = 4  # passou por uma revisão de 7 dias e outra de 14
DEFAULT_SETTINGS = {"min_level": "B1", "session_size": 8}
STRUCTURE_TYPES = {"choice", "reading", "listening", "flashcard", "sentence_order"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None = None) -> str:
    return (moment or now_utc()).isoformat(timespec="seconds")


def plain(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = text.replace("́", "").replace("'", "")
    text = unicodedata.normalize("NFC", text).replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def first_variant(value: str) -> str:
    return (value or "").split(",")[0].strip()


def main_meaning(pt: str) -> str:
    return (pt or "").split(";")[0].strip()


def normalize_answer(value: object) -> str:
    text = plain(str(value or ""))
    return re.sub(r"[.!?…]+$", "", text).strip()


# ============================================================================ áudio
SPOKEN_REPLACEMENTS = [
    (r"«([^»]*)»", r"\1"), (r"[“”\"]", ""), (r"\s*→\s*", " vira "), (r"\s*×\s*", " contra "),
    (r"\s*↔\s*", " e "), (r"\s*—\s*", ", "), (r"\s*–\s*", ", "),
    (r"(?<=[а-яёА-ЯЁa-zA-Z])\s*/\s*(?=[а-яёА-ЯЁa-zA-Z-])", " ou "),
    (r"\(([^()]{1,60})\)", r", \1,"), (r"\bB2\b", "bê dois"), (r"\bB1\b", "bê um"),
    (r"(?<![\wа-яёА-ЯЁ])-(?=[а-яёА-ЯЁ])", ""), (r"\s*;\s*", ". "), (r"\s*:\s*", ", "),
    (r"\s*\.{3,}\s*", ". "), (r"\s{2,}", " "), (r"\s+([,.!?])", r"\1"), (r"([,.])\s*([,.])+", r"\1"),
]


def spoken_text(text: str) -> str:
    result = str(text or "")
    for pattern, replacement in SPOKEN_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)
    return result.strip()


def lesson_script(unit: dict, block_index: int | None = None) -> str:
    blocks = unit.get("grammar") or []
    if block_index is not None:
        if block_index < 0 or block_index >= len(blocks):
            raise ValueError("Bloco de gramática inexistente nesta aula.")
        selected, parts = [blocks[block_index]], []
    else:
        selected, parts = blocks, [f"Aula: {unit.get('title', '')}."]
    if not selected:
        raise ValueError("Esta aula não tem explicação de gramática.")
    for block in selected:
        if block.get("audio_script"):
            parts.append(str(block["audio_script"]))
            continue
        if block.get("title"):
            parts.append(f"{block['title']}.")
        parts.extend(str(p) for p in block.get("paragraphs", []))
        for example in block.get("examples", []):
            if example.get("ru"):
                parts.append(f"Exemplo: {example['ru']}. Em português: {example.get('pt', '')}.")
    return " ".join(p.strip() for p in parts if str(p).strip())


class TTSService:
    """MP3 com edge-tts em cache; no Windows, cai para a voz russa instalada se o Edge recusar."""

    VOICE = "ru-RU-SvetlanaNeural"
    VOICES = {"f": ("ru-RU-SvetlanaNeural", "+0Hz"), "m": ("ru-RU-DmitryNeural", "+0Hz"),
              "f2": ("ru-RU-SvetlanaNeural", "-14Hz"), "m2": ("ru-RU-DmitryNeural", "+12Hz")}
    LESSON_VOICE = "pt-BR-ThalitaMultilingualNeural"
    EDGE_RETRY_SECONDS = 300

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._edge_down_until = 0.0
        self._endpoint_order = list(EDGE_ENDPOINTS)

    def _edge_synthesize(self, text: str, voice: str, rate: str, pitch: str, path: Path) -> None:
        last_error: Exception | None = None
        for endpoint in list(self._endpoint_order):
            edge_communicate.WSS_URL = endpoint.format(token=EDGE_TOKEN)
            try:
                edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save_sync(str(path))
            except Exception as exc:  # noqa: BLE001 - tenta o próximo endereço
                last_error = exc
                continue
            if path.exists() and path.stat().st_size > 0:
                self._endpoint_order.remove(endpoint)
                self._endpoint_order.insert(0, endpoint)
                return
            last_error = RuntimeError("O Edge não devolveu áudio.")
        raise last_error or RuntimeError("Nenhum endereço do Edge disponível.")

    def audio_for(self, text: str, mode: str = "target", speaker: str = "") -> Path:
        cleaned = re.sub(r"\s+", " ", text).strip()
        pitch = "+0Hz"
        if mode == "lesson":
            voice, rate, limit = self.LESSON_VOICE, "-6%", 7000
            cleaned = spoken_text(cleaned)
        elif speaker:
            if speaker not in self.VOICES:
                raise ValueError("Voz desconhecida.")
            voice, pitch = self.VOICES[speaker]
            rate, limit = "-6%", 800
        else:
            voice, rate, limit = self.VOICE, "-12%", 800
        if not cleaned or len(cleaned) > limit or not re.search(r"[A-Za-zÀ-žА-Яа-яЁё]", cleaned):
            raise ValueError(f"O texto do áudio deve ter de 1 a {limit} caracteres.")
        key = f"{voice}|{rate}|{cleaned}" if pitch == "+0Hz" else f"{voice}|{rate}|{pitch}|{cleaned}"
        target = self.cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.mp3"
        if target.exists() and target.stat().st_size > 0:
            return target
        offline_ok = mode != "lesson" and sys.platform == "win32"
        if edge_tts is None or (offline_ok and time.monotonic() < self._edge_down_until):
            if offline_ok:
                return self._offline_audio(cleaned)
            raise RuntimeError("edge-tts não está instalado.")
        temporary = target.with_suffix(f".{secrets.token_hex(6)}.tmp")
        with self._lock:
            if target.exists() and target.stat().st_size > 0:
                return target
            try:
                self._edge_synthesize(cleaned, voice, rate, pitch, temporary)
                temporary.replace(target)
                self._edge_down_until = 0.0
            except Exception:
                if not offline_ok:
                    raise
                self._edge_down_until = time.monotonic() + self.EDGE_RETRY_SECONDS
                return self._offline_audio(cleaned)
            finally:
                temporary.unlink(missing_ok=True)
        return target

    def _offline_audio(self, text: str) -> Path:
        folder = self.cache_dir.parent / "tts_offline"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}.wav"
        if target.exists() and target.stat().st_size > 0:
            return target
        temporary = target.with_suffix(f".{secrets.token_hex(6)}.tmp")
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ru-RU' } | Select-Object -First 1;"
            "if (-not $v) { exit 3 };"
            "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate = -1;"
            "$s.SetOutputToWaveFile($env:RUSSO_TTS_OUT); $s.Speak($env:RUSSO_TTS_TEXT); $s.Dispose()"
        )
        env = {**os.environ, "RUSSO_TTS_TEXT": text, "RUSSO_TTS_OUT": str(temporary)}
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                env=env, capture_output=True, timeout=30, creationflags=0x08000000,
            )
            if result.returncode == 3:
                raise RuntimeError("O Windows não tem voz em russo instalada (Configurações > Hora e idioma > Fala).")
            if result.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
                raise RuntimeError("A voz offline do Windows falhou.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target


# ============================================================================ léxico
GRAMMAR_LABELS = {
    "sg_nom": "nominativo sing.", "sg_gen": "genitivo sing.", "sg_dat": "dativo sing.", "sg_acc": "acusativo sing.",
    "sg_inst": "instrumental sing.", "sg_prep": "preposicional sing.", "pl_nom": "nominativo pl.", "pl_gen": "genitivo pl.",
    "pl_dat": "dativo pl.", "pl_acc": "acusativo pl.", "pl_inst": "instrumental pl.", "pl_prep": "preposicional pl.",
    "presfut_sg1": "1ª pessoa sing.", "presfut_sg2": "2ª pessoa sing.", "presfut_sg3": "3ª pessoa sing.",
    "presfut_pl1": "1ª pessoa pl.", "presfut_pl2": "2ª pessoa pl.", "presfut_pl3": "3ª pessoa pl.",
    "past_m": "passado masc.", "past_f": "passado fem.", "past_n": "passado neutro", "past_pl": "passado pl.",
    "imperative_sg": "imperativo", "imperative_pl": "imperativo pl.", "comparative": "comparativo",
    "superlative": "superlativo", "short_m": "forma curta masc.", "short_f": "forma curta fem.",
    "short_n": "forma curta neutra", "short_pl": "forma curta pl.",
}


CASE_LABELS = {"nom": "nominativo", "gen": "genitivo", "dat": "dativo", "acc": "acusativo", "inst": "instrumental", "prep": "preposicional"}
NUMBER_GENDER = {"m": "masc.", "f": "fem.", "n": "neutro", "pl": "pl."}


def grammar_label(column: str) -> str:
    if column.startswith("decl_"):
        _, gender, case = column.split("_")
        return f"{CASE_LABELS.get(case, case)} {NUMBER_GENDER.get(gender, gender)}"
    return GRAMMAR_LABELS.get(column, column)


def public_entry(entry: dict) -> dict:
    return {
        "id": entry["id"], "lemma": entry["lemma"], "accented": entry["accented"] or entry["lemma"],
        "pos": entry["pos"], "pos_label": POS_LABEL.get(entry["pos"], entry["pos"]),
        "level": entry["level"], "rank": entry["rank"], "pt": entry["pt"] or "",
        "gender": GENDER_LABEL.get(entry.get("gender") or "", ""),
        "aspect": {"imperfective": "imperfectivo", "perfective": "perfectivo", "both": "biaspectual"}.get(entry.get("aspect") or "", ""),
        "study": bool(entry["study"]),
    }


class Lexicon:
    """Base lexical somente leitura. Descompacta uma vez para a pasta de cache do aluno."""

    def __init__(self, gz_path: Path, cache_dir: Path):
        self.gz_path = gz_path
        self.cache_dir = cache_dir
        self.path, self.forms_path = self._prepare()
        self._local = threading.local()
        self.forms_ready = self.forms_path.exists()
        self._load()
        if not self.forms_ready:
            threading.Thread(target=self._build_form_index, daemon=True).start()

    def _prepare(self) -> tuple[Path, Path]:
        if not self.gz_path.exists():
            raise SystemExit(f"Base lexical ausente: {self.gz_path}. Rode tools/build_lexicon.py.")
        digest = hashlib.sha1()
        digest.update(str(self.gz_path.stat().st_size).encode())
        with open(self.gz_path, "rb") as handle:
            digest.update(handle.read(4 * 1024 * 1024))
        tag = digest.hexdigest()[:12]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / f"lexicon-{tag}.sqlite3"
        forms = self.cache_dir / f"forms-{tag}.sqlite3"
        if not target.exists():
            print("Preparando a base lexical (só na primeira abertura)...", flush=True)
            temporary = target.with_suffix(".tmp")
            with gzip.open(self.gz_path, "rb") as source, open(temporary, "wb") as out:
                shutil.copyfileobj(source, out)
            temporary.replace(target)
            for old in list(self.cache_dir.glob("lexicon-*.sqlite3")) + list(self.cache_dir.glob("forms-*.sqlite3")):
                if old not in (target, forms):
                    old.unlink(missing_ok=True)
        return target, forms

    def _build_form_index(self) -> None:
        """Índice forma -> verbete para o dicionário de clique; montado em segundo plano na primeira abertura."""
        temporary = self.forms_path.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        source = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        out = sqlite3.connect(temporary)
        out.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; CREATE TABLE form_index (form TEXT, entry_id INTEGER, grammar TEXT);")
        batch: list[tuple] = []
        for entry_id, lemma, forms in source.execute("SELECT id, lemma, forms FROM entries"):
            rows = {(plain(lemma), entry_id, "lemma")}
            for column, value in json.loads(forms or "{}").items():
                for variant in value.split(","):
                    form = plain(variant)
                    if form:
                        rows.add((form, entry_id, column))
            batch.extend(rows)
            if len(batch) > 50000:
                out.executemany("INSERT INTO form_index VALUES (?,?,?)", batch)
                batch = []
        out.executemany("INSERT INTO form_index VALUES (?,?,?)", batch)
        out.execute("CREATE INDEX idx_form ON form_index(form)")
        out.commit()
        out.close()
        source.close()
        temporary.replace(self.forms_path)
        self.forms_ready = True

    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _load(self) -> None:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        order = [t["id"] for t in json.loads(THEMES_PATH.read_text(encoding="utf-8"))["themes"]]
        stored = {row["id"]: json.loads(row["data"]) for row in conn.execute("SELECT id, data FROM themes")}
        self.themes = [stored[t] for t in order if t in stored] + [v for k, v in stored.items() if k not in order]
        self.theme_ids = [t["id"] for t in self.themes]
        self.entries: dict[int, dict] = {}
        for row in conn.execute(
            "SELECT id, lemma, accented, pos, rank, level, pt, study, gender, animate, aspect, partner, sg_only, pl_only, indeclinable FROM entries"
        ):
            self.entries[row["id"]] = dict(row)
        self.entry_themes: dict[int, list[str]] = defaultdict(list)
        self.theme_words: dict[str, list[int]] = defaultdict(list)
        for entry_id, theme in conn.execute("SELECT entry_id, theme_id FROM entry_themes ORDER BY score DESC"):
            self.entry_themes[entry_id].append(theme)
            self.theme_words[theme].append(entry_id)
        for ids in self.theme_words.values():
            ids.sort(key=lambda i: self.entries[i]["rank"])
        self.expressions: dict[int, dict] = {r["id"]: dict(r) for r in conn.execute("SELECT id, ru, pt, rank FROM expressions")}
        self.theme_expressions: dict[str, list[int]] = defaultdict(list)
        self.expression_themes: dict[int, list[str]] = defaultdict(list)
        for expr_id, theme in conn.execute("SELECT expression_id, theme_id FROM expression_themes"):
            self.theme_expressions[theme].append(expr_id)
            self.expression_themes[expr_id].append(theme)
        for ids in self.theme_expressions.values():
            ids.sort(key=lambda i: self.expressions[i]["rank"])
        self.content_themes: dict[str, list[str]] = defaultdict(list)
        for item_id, theme in conn.execute("SELECT item_id, theme_id FROM content_themes ORDER BY score DESC"):
            self.content_themes[item_id].append(theme)
        self.by_lemma: dict[str, list[int]] = defaultdict(list)
        self.pos_pool: dict[str, list[int]] = defaultdict(list)
        for entry_id, entry in sorted(self.entries.items(), key=lambda kv: kv[1]["rank"]):
            self.by_lemma[plain(entry["lemma"])].append(entry_id)
            if entry["study"]:
                self.pos_pool[entry["pos"]].append(entry_id)
        conn.close()

    def forms(self, entry_id: int) -> dict:
        row = self.conn().execute("SELECT forms FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return json.loads(row["forms"] or "{}") if row else {}

    def detail(self, entry_id: int) -> dict | None:
        entry = self.entries.get(entry_id)
        if not entry:
            return None
        partner = []
        for name in (entry.get("partner") or "").split(","):
            name = name.strip()
            if name:
                ids = self.by_lemma.get(plain(name), [])
                partner.append(self.entries[ids[0]]["accented"] if ids else name)
        return {**public_entry(entry), "forms": self.forms(entry_id), "themes": self.entry_themes.get(entry_id, []), "partner": partner}

    def lookup(self, word: str) -> dict:
        form = plain(word)
        if not form:
            return {"word": word, "entries": []}
        rows: list[tuple[int, str]] = []
        if self.forms_ready:
            conn = sqlite3.connect(f"file:{self.forms_path}?mode=ro", uri=True)
            try:
                rows = conn.execute("SELECT entry_id, GROUP_CONCAT(grammar, ',') FROM form_index WHERE form = ? GROUP BY entry_id", (form,)).fetchall()
            finally:
                conn.close()
        else:
            rows = [(i, "lemma") for i in self.by_lemma.get(form, [])]
        found = [(self.entries[i], g) for i, g in rows if i in self.entries]
        found.sort(key=lambda pair: (0 if plain(pair[0]["lemma"]) == form else 1, pair[0]["rank"]))
        return {
            "word": word, "ready": self.forms_ready,
            "entries": [
                {**public_entry(e), "themes": self.entry_themes.get(e["id"], []),
                 "grammar": [grammar_label(g) for g in dict.fromkeys((gram or "").split(",")) if g and g != "lemma"][:4]}
                for e, gram in found[:6]
            ],
        }

    def search(self, query: str, limit: int = 40) -> list[dict]:
        text = plain(query)
        if len(text) < 2:
            return []
        cyrillic = bool(re.search(r"[а-я]", text))
        results = []
        for entry in sorted(self.entries.values(), key=lambda e: e["rank"]):
            if cyrillic:
                hit = plain(entry["lemma"]).startswith(text)
            else:
                hit = bool(entry["pt"]) and any(
                    part.strip().lower().startswith(text) or f" {text}" in part.lower() for part in entry["pt"].split(";")
                )
            if hit:
                results.append(entry)
                if len(results) >= limit:
                    break
        return [{**public_entry(e), "themes": self.entry_themes.get(e["id"], [])} for e in results]


# ============================================================================ conteúdo reaproveitado
class Content:
    """Exercícios de gramática (unidades), construções (lições de vocabulário) e aulas narradas."""

    def __init__(self, lexicon: Lexicon):
        self.structures: dict[str, dict] = {}
        self.constructions: dict[str, dict] = {}
        self.units: dict[str, dict] = {}
        self.theme_structures: dict[str, list[str]] = defaultdict(list)
        self.theme_constructions: dict[str, list[str]] = defaultdict(list)
        self.theme_lessons: dict[str, list[str]] = defaultdict(list)
        unit_votes: dict[str, Counter] = defaultdict(Counter)
        for path in sorted(UNITS_DIR.glob("*.json")):
            unit = json.loads(path.read_text(encoding="utf-8"))
            if unit.get("course_id", "russian") != "russian":
                continue
            self.units[unit["id"]] = unit
            for exercise in unit.get("exercises", []):
                if exercise.get("type") not in STRUCTURE_TYPES:
                    continue
                item_id = f"g:{exercise['id']}"
                self.structures[item_id] = {**exercise, "unit_id": unit["id"], "unit_title": unit.get("title", "")}
                for theme in lexicon.content_themes.get(exercise["id"], ["essencial"]):
                    self.theme_structures[theme].append(item_id)
                    unit_votes[unit["id"]][theme] += 1
        if PREFIX_PATH.exists():
            prefix = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
            for exercise in prefix.get("exercises", []):
                item_id = f"g:{exercise['id']}"
                self.structures[item_id] = {**exercise, "type": exercise.get("type", "choice"), "unit_id": "", "unit_title": "Verbos com prefixo"}
                for theme in lexicon.content_themes.get(exercise["id"], ["essencial"]):
                    self.theme_structures[theme].append(item_id)
        for path in sorted(VOCAB_DIR.glob("*.json")):
            lesson = json.loads(path.read_text(encoding="utf-8"))
            for item in lesson.get("items", []):
                item_id = f"c:{lesson['id']}:{item['key']}"
                self.constructions[item_id] = {**item, "lesson_title": lesson.get("title", "")}
                for theme in lexicon.content_themes.get(f"{lesson['id']}:{item['key']}", ["essencial"]):
                    self.theme_constructions[theme].append(item_id)
        for unit_id, votes in unit_votes.items():
            if not self.units[unit_id].get("grammar"):
                continue
            total = sum(votes.values())
            for theme, count in votes.most_common(3):
                if count / total >= 0.2:
                    self.theme_lessons[theme].append(unit_id)

    def lesson_summary(self, unit_id: str) -> dict:
        unit = self.units[unit_id]
        return {"id": unit_id, "title": unit.get("title", ""), "minutes": unit.get("estimated_minutes")}


# ============================================================================ progresso
class Progress:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY, kind TEXT NOT NULL, theme_id TEXT,
                    stage INTEGER NOT NULL DEFAULT 0, due_at TEXT, seen_at TEXT NOT NULL, last_at TEXT,
                    last_success_day TEXT, correct INTEGER NOT NULL DEFAULT 0, wrong INTEGER NOT NULL DEFAULT 0,
                    lapses INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, item_id TEXT NOT NULL,
                    theme_id TEXT, exercise TEXT, mode TEXT, score REAL, answer TEXT, expected TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_items_due ON items(due_at);
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def settings(self) -> dict:
        with self.connect() as conn:
            stored = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM settings")}
        return {**DEFAULT_SETTINGS, **stored}

    def save_settings(self, values: dict) -> dict:
        clean = {}
        if values.get("min_level") in LEVELS:
            clean["min_level"] = values["min_level"]
        if str(values.get("session_size", "")).isdigit() and 4 <= int(values["session_size"]) <= 20:
            clean["session_size"] = int(values["session_size"])
        with self._lock, self.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", [(k, json.dumps(v)) for k, v in clean.items()])
        return self.settings()

    def states(self) -> dict[str, sqlite3.Row]:
        with self.connect() as conn:
            return {r["item_id"]: r for r in conn.execute("SELECT * FROM items")}

    def mark_seen(self, item_id: str, kind: str, theme_id: str) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO items (item_id, kind, theme_id, stage, due_at, seen_at) VALUES (?,?,?,0,?,?)",
                (item_id, kind, theme_id, iso(now_utc() + INTERVALS[0]), iso()),
            )

    def record(self, item_id: str, kind: str, theme_id: str, exercise: str, mode: str, score: float, answer: str, expected: str) -> dict:
        now = now_utc()
        today = now.astimezone().date().isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO items (item_id, kind, theme_id, stage, due_at, seen_at) VALUES (?,?,?,0,?,?)",
                (item_id, kind, theme_id, iso(now), iso(now)),
            )
            row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
            stage = row["stage"]
            if score >= 1:
                # O estágio sobe no máximo uma vez por dia: acertar três vezes na mesma sessão não prova memória de longo prazo.
                if row["last_success_day"] != today:
                    stage = min(stage + 1, len(INTERVALS) - 1)
                due = now + INTERVALS[stage]
                conn.execute(
                    "UPDATE items SET stage=?, due_at=?, last_at=?, last_success_day=?, correct=correct+1 WHERE item_id=?",
                    (stage, iso(due), iso(now), today, item_id),
                )
            elif score > 0:
                due = now + timedelta(hours=6)
                conn.execute("UPDATE items SET due_at=?, last_at=?, wrong=wrong+1 WHERE item_id=?", (iso(due), iso(now), item_id))
            else:
                stage = max(0, stage - 2)
                due = now + INTERVALS[0]
                conn.execute(
                    "UPDATE items SET stage=?, due_at=?, last_at=?, wrong=wrong+1, lapses=lapses+1 WHERE item_id=?",
                    (stage, iso(due), iso(now), item_id),
                )
            conn.execute(
                "INSERT INTO attempts (at, item_id, theme_id, exercise, mode, score, answer, expected) VALUES (?,?,?,?,?,?,?,?)",
                (iso(now), item_id, theme_id, exercise, mode, score, answer[:4000], expected[:4000]),
            )
        return {"stage": stage, "due_at": iso(due), "mastered": stage >= MASTERED_STAGE}

    def totals(self) -> dict:
        today = now_utc().astimezone().date()
        with self.connect() as conn:
            days = {r[0] for r in conn.execute("SELECT DISTINCT substr(at, 1, 10) FROM attempts ORDER BY 1 DESC LIMIT 400")}
            seen_total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            mastered = conn.execute("SELECT COUNT(*) FROM items WHERE stage >= ?", (MASTERED_STAGE,)).fetchone()[0]
            due = conn.execute("SELECT COUNT(*) FROM items WHERE due_at <= ?", (iso(),)).fetchone()[0]
        streak, day = 0, now_utc().date()
        if day.isoformat() not in days:
            day -= timedelta(days=1)
        while day.isoformat() in days:
            streak += 1
            day -= timedelta(days=1)
        return {"seen": seen_total, "mastered": mastered, "due": due, "streak": streak, "today": today.isoformat()}


# ============================================================================ motor do curso
class Course:
    def __init__(self, lexicon: Lexicon, content: Content, progress: Progress, lessons: LessonStore):
        self.lex = lexicon
        self.content = content
        self.progress = progress
        self.lessons = lessons
        self.pending: dict[str, dict] = {}  # token -> gabarito; o navegador só vê a resposta depois de responder
        self._lock = threading.Lock()

    # -- pertencimento e contagens
    def item_themes(self, item_id: str) -> list[str]:
        kind, _, rest = item_id.partition(":")
        if kind == "w":
            return self.lex.entry_themes.get(int(rest), [])
        if kind == "x":
            return self.lex.expression_themes.get(int(rest), [])
        if kind in ("g", "c"):
            return self.lex.content_themes.get(rest, ["essencial"])
        if kind == "l" and item_id in self.lessons.graded:
            return [self.lessons.lessons[self.lessons.graded[item_id][0]]["theme"]]
        return []

    def exists(self, item_id: str) -> bool:
        kind, _, rest = item_id.partition(":")
        if kind == "w":
            return rest.isdigit() and int(rest) in self.lex.entries
        if kind == "x":
            return rest.isdigit() and int(rest) in self.lex.expressions
        if kind == "g":
            return item_id in self.content.structures
        if kind == "c":
            return item_id in self.content.constructions
        if kind == "l":
            return item_id in self.lessons.graded
        return False

    def word_ids(self, theme_id: str, min_level: str) -> list[int]:
        allowed = set(LEVELS[LEVELS.index(min_level):])
        entries = self.lex.entries
        return [i for i in self.lex.theme_words.get(theme_id, []) if entries[i]["study"] and entries[i]["level"] in allowed]

    def expression_ids(self, theme_id: str) -> list[str]:
        return list(self.content.theme_constructions.get(theme_id, [])) + [f"x:{i}" for i in self.lex.theme_expressions.get(theme_id, [])]

    def theme(self, theme_id: str) -> dict:
        return next(t for t in self.lex.themes if t["id"] == theme_id)

    def overview(self) -> dict:
        settings = self.progress.settings()
        states = self.progress.states()
        now = iso()
        result = []
        for theme in self.lex.themes:
            tid = theme["id"]
            words = self.word_ids(tid, settings["min_level"])
            aspects = {a["id"]: {"id": a["id"], "label": a["label"], "total": 0, "seen": 0, "mastered": 0} for a in ASPECTS}
            levels = {lvl: {"total": 0, "seen": 0} for lvl in LEVELS}
            counters = {"due": 0}

            def tally(aspect_id: str, item_id: str) -> bool:
                bucket = aspects[aspect_id]
                bucket["total"] += 1
                state = states.get(item_id)
                if state is None:
                    return False
                bucket["seen"] += 1
                if state["stage"] >= MASTERED_STAGE:
                    bucket["mastered"] += 1
                if state["due_at"] and state["due_at"] <= now:
                    counters["due"] += 1
                return True

            new_words = 0
            for entry_id in words:
                entry = self.lex.entries[entry_id]
                seen = tally(POS_ASPECT[entry["pos"]], f"w:{entry_id}")
                levels[entry["level"]]["total"] += 1
                if seen:
                    levels[entry["level"]]["seen"] += 1
                else:
                    new_words += 1
            for item_id in self.content.theme_structures.get(tid, []):
                tally("estruturas", item_id)
            for item_id in self.expression_ids(tid):
                tally("expressoes", item_id)
            for item_id in self.lessons.theme_items(tid):
                tally(self.lessons.aspect(item_id), item_id)
            total = sum(a["total"] for a in aspects.values())
            result.append({
                **theme,
                "total": total,
                "seen": sum(a["seen"] for a in aspects.values()),
                "mastered": sum(a["mastered"] for a in aspects.values()),
                "due": counters["due"], "new_words": new_words,
                "aspects": list(aspects.values()),
                "levels": [{"level": k, **v} for k, v in levels.items() if v["total"]],
                "grammar_lessons": [self.content.lesson_summary(u) for u in self.content.theme_lessons.get(tid, [])],
                "modules": [self.lessons.summary(l, states) for l in self.lessons.by_theme.get(tid, [])],
                "preview": [self.lex.entries[i]["accented"] for i in words[:5]],
            })
        return {"themes": result, "settings": settings, "totals": self.progress.totals()}

    # -- exercícios
    def _token(self, payload: dict) -> str:
        token = secrets.token_urlsafe(9)
        with self._lock:
            if len(self.pending) > 20000:
                self.pending.clear()
            self.pending[token] = payload
        return token

    def _distractors(self, entry: dict, theme_id: str, field: str, count: int = 3) -> list[dict]:
        target_meanings = {m.strip().lower() for m in (entry["pt"] or "").split(";")}
        target_lemma = plain(entry["lemma"])
        entries = self.lex.entries
        pool = [i for i in self.lex.theme_words.get(theme_id, []) if entries[i]["pos"] == entry["pos"] and entries[i]["study"]]
        if len(pool) < 12:
            pool = self.lex.pos_pool[entry["pos"]]
        nearby = sorted(pool, key=lambda i: abs(entries[i]["rank"] - entry["rank"]))[:80]
        random.shuffle(nearby)
        chosen, seen_values = [], set()
        for candidate_id in nearby:
            candidate = entries[candidate_id]
            meaning = main_meaning(candidate["pt"]).lower()
            if candidate_id == entry["id"] or plain(candidate["lemma"]) == target_lemma or meaning in target_meanings:
                continue
            value = main_meaning(candidate["pt"]) if field == "pt" else candidate["accented"]
            if not value or value.lower() in seen_values:
                continue
            seen_values.add(value.lower())
            chosen.append(candidate)
            if len(chosen) >= count:
                break
        return chosen

    def word_intro(self, entry_id: int, theme_id: str) -> dict:
        return {"type": "intro", "kind": "word", "item_id": f"w:{entry_id}", "theme_id": theme_id, "word": self.lex.detail(entry_id)}

    def word_exercise(self, entry_id: int, theme_id: str, variant: str) -> dict | None:
        entry = self.lex.entries[entry_id]
        base = {"item_id": f"w:{entry_id}", "theme_id": theme_id, "kind": "word", "aspect": POS_ASPECT[entry["pos"]]}
        meaning = main_meaning(entry["pt"])
        if variant == "form":
            built = self._form_exercise(entry)
            if built:
                prompt, hint, answer, options = built
                token = self._token({**base, "exercise": "form", "answer": answer, "accept": [answer], "full": entry["pt"]})
                return {**base, "type": "choice", "exercise": "form", "token": token, "instruction": "Escolha a forma correta.",
                        "prompt": prompt, "prompt_ru": True, "hint": hint, "options": options, "ru_options": True}
            variant = "pt_ru"
        if variant == "type":
            token = self._token({**base, "exercise": "type", "answer": entry["accented"], "accept": [entry["lemma"]], "typed": True, "full": entry["pt"]})
            return {**base, "type": "input", "exercise": "type", "token": token, "instruction": "Escreva em russo (forma de dicionário).",
                    "prompt": meaning, "hint": POS_LABEL[entry["pos"]]}
        if variant == "pt_ru":
            others = self._distractors(entry, theme_id, "ru")
            options = [entry["accented"]] + [o["accented"] for o in others]
            random.shuffle(options)
            token = self._token({**base, "exercise": "pt_ru", "answer": entry["accented"], "accept": [entry["accented"]], "full": entry["pt"]})
            return {**base, "type": "choice", "exercise": "pt_ru", "token": token, "instruction": "Qual é a palavra russa?",
                    "prompt": meaning, "hint": POS_LABEL[entry["pos"]], "options": options, "ru_options": True}
        others = self._distractors(entry, theme_id, "pt")
        options = [meaning] + [main_meaning(o["pt"]) for o in others]
        random.shuffle(options)
        token = self._token({**base, "exercise": variant, "answer": meaning, "accept": [meaning], "full": entry["pt"],
                             "transcript": entry["accented"] if variant == "audio" else ""})
        if variant == "audio":
            return {**base, "type": "choice", "exercise": "audio", "token": token, "instruction": "Ouça e escolha o significado.",
                    "audio": entry["lemma"], "prompt": "", "options": options}
        return {**base, "type": "choice", "exercise": "ru_pt", "token": token, "instruction": "O que significa?",
                "prompt": entry["accented"], "prompt_ru": True, "audio": entry["lemma"], "options": options}

    def _form_exercise(self, entry: dict):
        forms = self.lex.forms(entry["id"])
        if entry["pos"] == "noun" and not entry.get("indeclinable"):
            numbers = ["pl"] if entry.get("pl_only") else ["sg"] if entry.get("sg_only") else ["sg", "sg", "pl"]
            number = random.choice(numbers)
            templates = [("gen", "без", "genitivo"), ("dat", "к", "dativo"), ("inst", "с", "instrumental"),
                         ("prep", "о", "preposicional"), ("acc", "Я вижу", "acusativo")]
            random.shuffle(templates)
            for case, lead, label in templates:
                target = first_variant(forms.get(f"{number}_{case}", ""))
                if not target or plain(target) == plain(first_variant(forms.get(f"{number}_nom", ""))):
                    continue
                if lead == "о" and plain(target)[:1] in "аоуэиы":
                    lead = "об"
                pool = [first_variant(forms.get(f"{number}_{c}", "")) for c in ("nom", "gen", "dat", "acc", "inst", "prep")]
                pool.append(first_variant(forms.get(f"{'pl' if number == 'sg' else 'sg'}_{case}", "")))
                others = list({plain(f): f for f in pool if f and plain(f) != plain(target)}.values())
                if len(others) < 3:
                    continue
                options = [target] + random.sample(others, 3)
                random.shuffle(options)
                return f"{lead} ___", f"{entry['accented']} · {label} {'singular' if number == 'sg' else 'plural'}", target, options
        if entry["pos"] == "verb":
            persons = [("presfut_sg1", "я"), ("presfut_sg2", "ты"), ("presfut_sg3", "она"), ("presfut_pl1", "мы"),
                       ("presfut_pl2", "вы"), ("presfut_pl3", "они"), ("past_f", "вчера она"), ("past_pl", "вчера они")]
            random.shuffle(persons)
            for column, pronoun in persons:
                target = first_variant(forms.get(column, ""))
                if not target:
                    continue
                pool = [first_variant(forms.get(c, "")) for c, _ in persons if c != column]
                others = list({plain(f): f for f in pool if f and plain(f) != plain(target)}.values())
                if len(others) < 3:
                    continue
                options = [target] + random.sample(others, 3)
                random.shuffle(options)
                tense = "passado" if column.startswith("past") else ("futuro" if entry.get("aspect") == "perfective" else "presente")
                return f"{pronoun[0].upper()}{pronoun[1:]} ___", f"{entry['accented']} · {tense}", target, options
        if entry["pos"] == "adjective":
            choices = [("decl_f_nom", "___ книга", "feminino"), ("decl_n_nom", "___ место", "neutro"),
                       ("decl_pl_nom", "___ люди", "plural"), ("decl_m_gen", "без ___ стола", "genitivo masculino"),
                       ("decl_f_inst", "с ___ книгой", "instrumental feminino")]
            random.shuffle(choices)
            for column, frame, label in choices:
                target = first_variant(forms.get(column, ""))
                if not target:
                    continue
                pool = [first_variant(forms.get(c, "")) for c in ("decl_m_nom", "decl_f_nom", "decl_n_nom", "decl_pl_nom", "decl_m_gen", "decl_f_acc", "decl_f_inst")]
                others = list({plain(f): f for f in pool if f and plain(f) != plain(target)}.values())
                if len(others) < 3:
                    continue
                options = [target] + random.sample(others, 3)
                random.shuffle(options)
                return frame, f"{entry['accented']} · {label}", target, options
        return None

    def structure_exercise(self, item_id: str, theme_id: str) -> dict:
        exercise = self.content.structures[item_id]
        base = {"item_id": item_id, "theme_id": theme_id, "kind": "structure", "aspect": "estruturas",
                "unit_title": exercise.get("unit_title", ""), "instruction": exercise.get("instruction", ""), "prompt": exercise.get("prompt", "")}
        etype = exercise["type"]
        if etype == "flashcard":
            token = self._token({**base, "exercise": "flashcard", "answer": exercise.get("back", ""), "self_rated": True,
                                 "explanation": exercise.get("explanation", "")})
            return {**base, "type": "flashcard", "exercise": "flashcard", "token": token, "front": exercise.get("front", ""),
                    "back": exercise.get("back", ""), "explanation": exercise.get("explanation", ""),
                    "instruction": "Lembre a regência e depois confira."}
        if etype == "sentence_order":
            tokens = list(exercise.get("tokens", []))
            while len(tokens) > 1 and tokens == list(exercise.get("tokens", [])):
                random.shuffle(tokens)
            token = self._token({**base, "exercise": "order", "answer": exercise.get("answer", ""), "accept": [exercise.get("answer", "")],
                                 "explanation": exercise.get("explanation", "")})
            return {**base, "type": "order", "exercise": "order", "token": token, "tokens": tokens}
        options = list(exercise.get("options", []))
        random.shuffle(options)
        accept = [exercise.get("answer", "")] + list(exercise.get("valid_answers", []))
        token = self._token({**base, "exercise": etype, "answer": exercise.get("answer", ""), "accept": accept,
                             "explanation": exercise.get("explanation", ""), "transcript": exercise.get("audio_text", "")})
        public = {**base, "type": "choice", "exercise": etype, "token": token, "options": options,
                  "prompt_ru": bool(re.search(r"[а-яё]", (exercise.get("prompt") or "").lower())),
                  "ru_options": bool(options and re.search(r"[а-яё]", str(options[0]).lower()))}
        if etype == "reading":
            public["context"] = exercise.get("context", "")
        if etype == "listening":
            public["audio"] = exercise.get("audio_text", "")
        return public

    def construction_intro(self, item_id: str, theme_id: str) -> dict:
        item = self.content.constructions[item_id]
        keys = ("head", "regency", "case", "pt", "chunk", "chunk_pt", "form_note", "trap", "example")
        return {"type": "intro", "kind": "construction", "item_id": item_id, "theme_id": theme_id,
                "construction": {k: item.get(k) for k in keys}}

    def construction_exercise(self, item_id: str, theme_id: str, variant: str | None = None) -> dict:
        item = self.content.constructions[item_id]
        base = {"item_id": item_id, "theme_id": theme_id, "kind": "construction", "aspect": "expressoes"}
        variants = [v for v in ("chunk", "cloze", "hear") if item.get("chunk_wrong" if v == "chunk" else v)]
        variant = variant if variant in variants else random.choice(variants or ["chunk"])
        if variant == "cloze":
            cloze = item["cloze"]
            options = [cloze["answer"]] + list(cloze.get("wrong", []))[:3]
            random.shuffle(options)
            token = self._token({**base, "exercise": "cloze", "answer": cloze["answer"], "accept": [cloze["answer"]],
                                 "explanation": cloze.get("note", ""), "translation": cloze.get("pt", "")})
            return {**base, "type": "choice", "exercise": "cloze", "token": token, "instruction": "Complete a frase.",
                    "prompt": cloze["ru"], "prompt_ru": True, "options": options, "ru_options": True}
        if variant == "hear":
            hear = item["hear"]
            options = [hear["pt"]] + list(hear.get("wrong", []))[:3]
            random.shuffle(options)
            token = self._token({**base, "exercise": "hear", "answer": hear["pt"], "accept": [hear["pt"]],
                                 "explanation": hear.get("note", ""), "transcript": hear["ru"]})
            return {**base, "type": "choice", "exercise": "hear", "token": token, "instruction": "Ouça e escolha a tradução.",
                    "audio": hear["ru"], "prompt": "", "options": options}
        options = [item["chunk"]] + list(item.get("chunk_wrong", []))[:3]
        random.shuffle(options)
        token = self._token({**base, "exercise": "chunk", "answer": item["chunk"], "accept": [item["chunk"]],
                             "explanation": item.get("form_note", ""), "translation": item.get("chunk_pt", "")})
        return {**base, "type": "choice", "exercise": "chunk", "token": token, "instruction": "Qual construção está correta?",
                "prompt": item.get("chunk_pt") or item.get("pt", ""), "options": options, "ru_options": True}

    def expression_intro(self, expr_id: int, theme_id: str) -> dict:
        expr = self.lex.expressions[expr_id]
        return {"type": "intro", "kind": "expression", "item_id": f"x:{expr_id}", "theme_id": theme_id,
                "expression": {"ru": expr["ru"], "pt": expr["pt"]}}

    def expression_exercise(self, expr_id: int, theme_id: str, variant: str = "ru_pt") -> dict:
        expr = self.lex.expressions[expr_id]
        pool = [i for i in self.lex.theme_expressions.get(theme_id, []) if i != expr_id]
        if len(pool) < 6:
            pool = list(self.lex.expressions)
        sample = random.sample(pool, min(14, len(pool)))
        base = {"item_id": f"x:{expr_id}", "theme_id": theme_id, "kind": "expression", "aspect": "expressoes"}
        to_pt = variant == "ru_pt"
        target = main_meaning(expr["pt"]) if to_pt else expr["ru"]
        others: list[str] = []
        for candidate in sample:
            value = main_meaning(self.lex.expressions[candidate]["pt"]) if to_pt else self.lex.expressions[candidate]["ru"]
            if value and value != target and value not in others:
                others.append(value)
            if len(others) == 3:
                break
        options = [target] + others
        random.shuffle(options)
        token = self._token({**base, "exercise": variant, "answer": target, "accept": [target], "translation": expr["pt"]})
        if to_pt:
            return {**base, "type": "choice", "exercise": "ru_pt", "token": token, "instruction": "O que significa a expressão?",
                    "prompt": expr["ru"], "prompt_ru": True, "audio": expr["ru"], "options": options}
        return {**base, "type": "choice", "exercise": "pt_ru", "token": token, "instruction": "Como se diz em russo?",
                "prompt": main_meaning(expr["pt"]), "options": options, "ru_options": True}

    def retry(self, item_id: str, theme_id: str, variant: str) -> dict | None:
        """Nova versão da mesma pergunta para voltar mais adiante na sessão depois de um erro."""
        kind, _, rest = item_id.partition(":")
        if not self.exists(item_id):
            return None
        if kind == "w":
            return self.word_exercise(int(rest), theme_id, variant if variant in ("ru_pt", "pt_ru", "audio", "form", "type") else "ru_pt")
        if kind == "x":
            return self.expression_exercise(int(rest), theme_id, variant if variant in ("ru_pt", "pt_ru") else "ru_pt")
        if kind == "c":
            return self.construction_exercise(item_id, theme_id, variant)
        if kind == "l":
            return self.lessons.screen(item_id, theme_id, self._token)
        return self.structure_exercise(item_id, theme_id)

    # -- sessões
    def study_session(self, theme_id: str) -> dict:
        settings = self.progress.settings()
        states = self.progress.states()
        size = int(settings["session_size"])
        new_words = [i for i in self.word_ids(theme_id, settings["min_level"]) if f"w:{i}" not in states][:size]
        new_structures = [i for i in self.content.theme_structures.get(theme_id, []) if i not in states][:2]
        new_expressions = [i for i in self.expression_ids(theme_id) if i not in states][:2]
        steps: list[dict | None] = []
        for start in range(0, len(new_words), 4):
            chunk = new_words[start:start + 4]
            steps += [self.word_intro(i, theme_id) for i in chunk]
            for variant in ("ru_pt", "pt_ru"):
                quiz = [self.word_exercise(i, theme_id, variant) for i in chunk]
                random.shuffle(quiz)
                steps += quiz
        for item_id in new_expressions:
            if item_id.startswith("c:"):
                steps += [self.construction_intro(item_id, theme_id), self.construction_exercise(item_id, theme_id, "chunk")]
            else:
                expr_id = int(item_id[2:])
                steps += [self.expression_intro(expr_id, theme_id), self.expression_exercise(expr_id, theme_id, "ru_pt")]
        steps += [self.structure_exercise(item_id, theme_id) for item_id in new_structures]
        recap = [self.word_exercise(i, theme_id, "form") for i in new_words if self.lex.entries[i]["pos"] != "other"]
        random.shuffle(recap)
        steps += recap[:4]
        return {"mode": "study", "theme": self.theme(theme_id), "steps": [s for s in steps if s],
                "new_items": len(new_words) + len(new_structures) + len(new_expressions)}

    def review_session(self, theme_id: str, extra: bool = False) -> dict:
        states = self.progress.states()
        now = iso()
        mine = [s for s in states.values() if self.exists(s["item_id"]) and theme_id in self.item_themes(s["item_id"])
                and (not s["item_id"].startswith("l:") or self.lessons.reviewable(s["item_id"]))]
        due = sorted([s for s in mine if s["due_at"] and s["due_at"] <= now], key=lambda s: s["due_at"])
        size = 20
        chosen = due[:size]
        if (extra or not chosen) and len(chosen) < size:
            taken = {s["item_id"] for s in chosen}
            rest = sorted([s for s in mine if s["item_id"] not in taken], key=lambda s: (s["stage"], -s["lapses"], s["last_at"] or ""))
            chosen += rest[: size - len(chosen)]
        steps = []
        for state in chosen:
            item_id, stage = state["item_id"], state["stage"]
            kind, _, rest = item_id.partition(":")
            if kind == "w":
                variants = ["ru_pt", "pt_ru"] if stage <= 1 else ["audio", "form", "pt_ru"] if stage <= 3 else ["type", "form", "audio"]
                steps.append(self.word_exercise(int(rest), theme_id, random.choice(variants)))
            elif kind == "g":
                steps.append(self.structure_exercise(item_id, theme_id))
            elif kind == "c":
                steps.append(self.construction_exercise(item_id, theme_id))
            elif kind == "x":
                steps.append(self.expression_exercise(int(rest), theme_id, random.choice(["ru_pt", "pt_ru"])))
            elif kind == "l" and self.lessons.reviewable(item_id):
                steps.append(self.lessons.screen(item_id, theme_id, self._token))
        random.shuffle(steps)
        return {"mode": "review", "theme": self.theme(theme_id), "steps": [s for s in steps if s], "due": len(due)}

    def lesson_session(self, lesson_id: str, part: int) -> dict:
        if lesson_id not in self.lessons.lessons:
            raise ValueError("Aula desconhecida.")
        lesson = self.lessons.lessons[lesson_id]
        if not 0 <= part < len(lesson["parts"]):
            raise ValueError("Parte inexistente.")
        theme_id = lesson["theme"]
        steps = self.lessons.screens(lesson_id, part, theme_id, self._token)
        return {"mode": "lesson", "theme": self.theme(theme_id), "steps": steps, "lesson_id": lesson_id, "part": part,
                "part_title": lesson["parts"][part]["title"], "lesson_title": lesson["title"]}

    def answer(self, payload: dict) -> dict:
        with self._lock:
            pending = self.pending.pop(str(payload.get("token", "")), None)
        if not pending:
            raise ValueError("Esta pergunta expirou. Feche a sessão e comece outra.")
        given = payload.get("answer", "")
        note = ""
        extra: dict = {}
        if "answers" in pending:  # texto com lacunas
            score, marks = grade_cloze(pending, given if isinstance(given, list) else [])
            extra = {"marks": marks, "answers": pending["answers"]}
            given = " | ".join(str(g) for g in given) if isinstance(given, list) else str(given)
        elif "pairs" in pending:  # relacionar
            score, pairs = grade_match(pending, given if isinstance(given, list) else [])
            extra = {"pairs": pairs}
            given = "; ".join(f"{p.get('left')} = {p.get('right')}" for p in given if isinstance(p, dict)) if isinstance(given, list) else ""
        elif pending.get("exercise") == "produce":
            checklist = pending.get("checklist") or []
            checked = max(0, min(len(checklist), int(payload.get("checked", 0) or 0)))
            score = checked / len(checklist) if checklist else 1.0
            extra = {"model": pending.get("answer", "")}
        elif pending.get("self_rated"):
            score = {1: 0.0, 2: 0.5, 3: 1.0}.get(int(payload.get("rating", 0) or 0), 0.0)
        elif pending.get("exercise") == "dictation":
            score, words = dictation_score(str(given), pending["answer"])
            extra = {"words": words}
            note = "" if score >= 1 else "Palavras em vermelho faltaram ou foram escritas de outro modo."
        elif pending.get("typed"):
            score, note = typed_score(str(given), pending["accept"])
        else:
            score = 1.0 if any(normalize_answer(given) == normalize_answer(a) for a in pending.get("accept", []) if a) else 0.0
        state = self.progress.record(pending["item_id"], pending["kind"], pending["theme_id"], pending.get("exercise", ""),
                                     str(payload.get("mode", "")), score, str(given), str(pending.get("answer", "")))
        return {
            "score": score, "correct": score >= 1, "partial": 0 < score < 1, "note": note,
            "answer": pending.get("answer", ""), "full": pending.get("full", ""),
            "explanation": pending.get("explanation", ""), "translation": pending.get("translation", ""),
            "transcript": pending.get("transcript", ""), "state": state, **extra,
        }

    def theme_items(self, theme_id: str, aspect: str, offset: int) -> dict:
        settings = self.progress.settings()
        states = self.progress.states()
        if aspect in ("estruturas", "expressoes", "leitura", "escuta", "producao"):
            lesson_ids = [i for i in self.lessons.theme_items(theme_id) if self.lessons.aspect(i) == aspect]
            ids = lesson_ids + (self.content.theme_structures.get(theme_id, []) if aspect == "estruturas"
                                else self.expression_ids(theme_id) if aspect == "expressoes" else [])
            rows = []
            for item_id in ids[offset:offset + 60]:
                state = states.get(item_id)
                if item_id.startswith("l:"):
                    ru, pt = self.lessons.label(item_id)
                elif item_id.startswith("g:"):
                    ex = self.content.structures[item_id]
                    ru, pt = ex.get("prompt") or ex.get("front", ""), ex.get("unit_title", "")
                elif item_id.startswith("c:"):
                    item = self.content.constructions[item_id]
                    ru, pt = item.get("head", ""), item.get("pt", "")
                else:
                    expr = self.lex.expressions[int(item_id[2:])]
                    ru, pt = expr["ru"], expr["pt"]
                rows.append({"item_id": item_id, "ru": ru, "pt": pt, "stage": state["stage"] if state else None})
            return {"items": rows, "total": len(ids), "offset": offset}
        pos = next((a["pos"] for a in ASPECTS if a["id"] == aspect and a["kind"] == "word"), None)
        ids = [i for i in self.word_ids(theme_id, settings["min_level"]) if pos is None or self.lex.entries[i]["pos"] == pos]
        rows = []
        for entry_id in ids[offset:offset + 60]:
            entry = self.lex.entries[entry_id]
            state = states.get(f"w:{entry_id}")
            rows.append({**public_entry(entry), "ru": entry["accented"], "item_id": f"w:{entry_id}", "stage": state["stage"] if state else None})
        return {"items": rows, "total": len(ids), "offset": offset}


WORD = re.compile(r"[\wЁё-]+")


def dictation_score(given: str, expected: str) -> tuple[float, list[dict]]:
    """Ditado: compara palavra por palavra (sem caixa, pontuação, acento e ё) e dá crédito proporcional."""
    target_words = WORD.findall(expected)
    target = [normalize_answer(w) for w in target_words]
    typed = [normalize_answer(w) for w in WORD.findall(given)]
    matcher = difflib.SequenceMatcher(None, typed, target, autojunk=False)
    hits: set[int] = set()
    for block in matcher.get_matching_blocks():
        hits.update(range(block.b, block.b + block.size))
    words = [{"w": word, "ok": index in hits} for index, word in enumerate(target_words)]
    if not target:
        return 0.0, words
    score = len(hits) / len(target)
    if score >= 1 and len(typed) != len(target):
        score = 0.9  # palavras a mais
    return round(score, 2), words


def typed_score(given: str, accepted: list[str]) -> tuple[float, str]:
    answer = normalize_answer(given)
    best = 0.0
    for target in accepted:
        expected = normalize_answer(target)
        if answer == expected:
            return 1.0, ""
        if difflib.SequenceMatcher(None, answer, expected).ratio() >= 0.85:
            best = 0.5
    return best, ("Quase: confira a grafia." if best else "")


# ============================================================================ HTTP
class AppHandler(BaseHTTPRequestHandler):
    server_version = "LinguaLab/2.0"

    @property
    def app(self) -> "AppServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data: object, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_audio(self, path: Path) -> None:
        raw = path.read_bytes()
        offline = path.suffix == ".wav"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav" if offline else "audio/mpeg")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store" if offline else "public, max-age=31536000, immutable")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Corpo da requisição grande demais")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.serve_static(parsed.path)
            return
        try:
            self.handle_get(parsed.path, {k: v[0] for k, v in parse_qs(parsed.query).items()})
        except (KeyError, ValueError, StopIteration) as exc:
            self.send_json({"error": str(exc) or "Pedido inválido."}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        app = self.app
        try:
            if parsed.path == "/api/answer":
                self.send_json(app.course.answer(payload))
            elif parsed.path == "/api/seen":
                item_id = str(payload.get("item_id", ""))
                if not app.course.exists(item_id):
                    raise ValueError("Item desconhecido.")
                app.progress.mark_seen(item_id, item_id.split(":")[0], str(payload.get("theme_id", "")))
                self.send_json({"ok": True})
            elif parsed.path == "/api/settings":
                self.send_json(app.progress.save_settings(payload))
            elif parsed.path == "/api/window/focus":
                app.focus_window()
                self.send_json({"ok": True, "window": app.window is not None})
            elif parsed.path == "/api/update/apply":
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).netloc != self.headers.get("Host"):
                    self.send_json({"error": "Origem não permitida."}, HTTPStatus.FORBIDDEN)
                    return
                app.updater.start_apply()
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "Endpoint não encontrado"}, HTTPStatus.NOT_FOUND)
        except (ValueError, UpdateError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_get(self, path: str, q: dict[str, str]) -> None:
        app = self.app
        if path == "/api/bootstrap":
            lex = app.lexicon
            self.send_json({
                "app_version": APP_VERSION, "aspects": ASPECTS, "levels": LEVELS,
                "features": {"tts": edge_tts is not None or sys.platform == "win32", "self_update": FROZEN},
                "counts": {"entries": len(lex.entries), "studyable": sum(1 for e in lex.entries.values() if e["study"]),
                           "expressions": len(lex.expressions) + len(app.content.constructions),
                           "structures": len(app.content.structures), "themes": len(lex.themes),
                           "lessons": len(app.lessons.lessons), "lesson_items": len(app.lessons.graded)},
                **app.course.overview(),
            })
        elif path == "/api/themes":
            self.send_json(app.course.overview())
        elif path == "/api/session":
            theme_id = q.get("theme", "")
            if theme_id not in app.lexicon.theme_ids:
                raise ValueError("Tema desconhecido.")
            if q.get("mode") == "review":
                self.send_json(app.course.review_session(theme_id, extra=q.get("extra") == "1"))
            else:
                self.send_json(app.course.study_session(theme_id))
        elif path == "/api/aula":
            self.send_json(app.course.lesson_session(q.get("id", ""), int(q.get("part", "0") or 0)))
        elif path == "/api/retry":
            self.send_json(app.course.retry(q.get("item_id", ""), q.get("theme", ""), q.get("variant", "")) or {"error": "Item desconhecido."})
        elif path == "/api/theme/items":
            self.send_json(app.course.theme_items(q.get("theme", ""), q.get("aspect", ""), max(0, int(q.get("offset", "0") or 0))))
        elif path == "/api/word":
            detail = app.lexicon.detail(int(q.get("id", "0")))
            if not detail:
                self.send_json({"error": "Palavra não encontrada."}, HTTPStatus.NOT_FOUND)
                return
            state = app.progress.states().get(f"w:{detail['id']}")
            detail["state"] = {"stage": state["stage"], "due_at": state["due_at"]} if state else None
            self.send_json(detail)
        elif path == "/api/dictionary":
            self.send_json(app.lexicon.lookup(q.get("word", "")))
        elif path == "/api/search":
            self.send_json({"results": app.lexicon.search(q.get("q", ""))})
        elif path == "/api/lesson":
            unit = app.content.units.get(q.get("unit_id", ""))
            if not unit:
                self.send_json({"error": "Aula não encontrada."}, HTTPStatus.NOT_FOUND)
                return
            keys = ("id", "title", "description", "objectives", "grammar", "memory_table", "memory_tables", "source_note")
            self.send_json({k: unit.get(k) for k in keys if unit.get(k) is not None})
        elif path in ("/api/tts", "/api/lesson-audio"):
            try:
                if path == "/api/tts":
                    audio = app.tts.audio_for(q.get("text", ""), speaker=q.get("voice", ""))
                else:
                    unit = app.content.units.get(q.get("unit_id", ""))
                    if not unit:
                        raise ValueError("Aula não encontrada.")
                    block = q.get("block", "all")
                    audio = app.tts.audio_for(lesson_script(unit, None if block in ("", "all") else int(block)), mode="lesson")
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": f"Não foi possível gerar o áudio: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_audio(audio)
        elif path == "/api/update/check":
            self.send_json(app.updater.check(force=q.get("force") == "1"))
        elif path == "/api/update/status":
            self.send_json(app.updater.status())
        else:
            self.send_json({"error": "Endpoint não encontrado"}, HTTPStatus.NOT_FOUND)

    def serve_static(self, path: str) -> None:
        path = unquote(path)
        if path == "/":
            path = "/index.html"
        candidate = (STATIC_DIR / path.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
        raw = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", types.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]):
        self.lexicon = Lexicon(LEXICON_GZ, CACHE_DIR)
        self.content = Content(self.lexicon)
        self.progress = Progress(DB_PATH)
        self.lessons = LessonStore(LESSONS_DIR)
        self.course = Course(self.lexicon, self.content, self.progress, self.lessons)
        self.tts = TTSService(TTS_CACHE_DIR)
        self.window = None
        self.updater = Updater(APP_VERSION, USER_DIR, on_restart=self.request_quit)
        super().__init__(address, handler)

    def request_quit(self) -> None:
        if self.window is not None:
            self.window.destroy()
        else:
            threading.Thread(target=self.shutdown, daemon=True).start()

    def focus_window(self) -> None:
        if self.window is None:
            return
        self.window.restore()
        self.window.show()
        self.window.on_top = True
        self.window.on_top = False


def already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/update/status", timeout=1.5) as response:
            return "phase" in json.load(response)
    except Exception:  # noqa: BLE001
        return False


WINDOW_TITLE = "LinguaLab · Русский"
LOG_MAX_BYTES = 2_000_000


def redirect_output_if_windowless() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    USER_DIR.mkdir(parents=True, exist_ok=True)
    log_path = USER_DIR / "app.log"
    if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
        log_path.unlink()
    log = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def focus_running_window(url: str) -> bool:
    request = urllib.request.Request(f"{url}/api/window/focus", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return bool(json.load(response).get("window"))
    except Exception:  # noqa: BLE001
        return False


def run_in_window(server: AppServer, url: str, title: str = WINDOW_TITLE) -> bool:
    try:
        import webview
    except ImportError:
        return False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        server.window = webview.create_window(title, url, width=1320, height=880, min_size=(900, 640), background_color="#E9ECE8")
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(USER_DIR / "webview"))
    except Exception as exc:  # noqa: BLE001
        print(f"Janela própria indisponível ({exc}); abrindo no navegador.")
        server.window = None
        webbrowser.open(url)
        thread.join()
        return True
    server.shutdown()
    return True


def main() -> None:
    redirect_output_if_windowless()
    parser = argparse.ArgumentParser(description="LinguaLab Russo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true", help="abrir no navegador em vez da janela própria")
    parser.add_argument("--no-browser", action="store_true", help="só o servidor, sem abrir interface")
    parser.add_argument("--data-dir", help="pasta de dados do aluno (padrão: %%APPDATA%%\\RussoTrainer)")
    parser.add_argument("--title", default=WINDOW_TITLE, help="título da janela")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    url = f"http://{args.host}:{args.port}"
    if already_running(url):
        print(f"LinguaLab já está aberto em {url}")
        if not focus_running_window(url) and not args.no_browser:
            webbrowser.open(url)
        return
    server = AppServer((args.host, args.port), AppHandler)
    print(f"LinguaLab disponível em {url}")
    try:
        if not args.browser and not args.no_browser and run_in_window(server, url, args.title):
            return
        print("Pressione Ctrl+C para encerrar.")
        if not args.no_browser:
            threading.Timer(0.7, lambda: webbrowser.open(url)).start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
