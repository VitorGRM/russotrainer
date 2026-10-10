#!/usr/bin/env python3
"""LinguaLab — servidor local, corretor e registro pedagógico multilíngue.

A interface e a persistência usam a biblioteca padrão. O áudio usa edge-tts.
O conteúdo fica em data/units/*.json; respostas em data/progress.sqlite3.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import random
import re
import secrets
import sqlite3
import sys
import subprocess
import threading
import time
import unicodedata
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse


try:
    import edge_tts
except ImportError:  # O run.sh instala; fallback permite diagnóstico legível.
    edge_tts = None

from sessions import SessionStore, unit_session_order
from updater import Updater, UpdateError
from vocab_lessons import UNGRADED_TYPES, VOCAB_UNIT_PREFIX, VocabLessonStore


APP_VERSION = "1.5.1"
UNIT_COMPLETION_THRESHOLD = 0.75
# Domínio cumulativo: um exercício é considerado "dominado" se o aluno atingiu
# QUALQUER um destes patamares (nota mínima, nº de tentativas que bateram essa
# nota). Isto recompensa quem acerta "quase certo" com consistência tanto
# quanto quem acerta de primeira com nota alta — em vez de exigir nota máxima
# numa única tentativa.
MASTERY_TIERS: list[tuple[float, int]] = [(0.75, 1), (0.60, 3), (0.50, 5)]
FROZEN = bool(getattr(sys, "frozen", False))
# No .exe, o conteúdo (somente leitura) vem empacotado; o que o aluno gera fica em
# %APPDATA%\RussoTrainer para sobreviver às atualizações. Em desenvolvimento nada muda.
BASE_DIR = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)
USER_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "RussoTrainer" if FROZEN else BASE_DIR
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
UNITS_DIR = DATA_DIR / "units"
PREFIX_VERBS_PATH = DATA_DIR / "prefix_verbs.json"
PREFIX_VERBS_UNIT_ID = "prefix_verbs"
VOCAB_LESSONS_DIR = DATA_DIR / "vocab_lessons"
EXPORT_DIR = Path(os.environ.get("RUSSO_EXPORT_DIR", str(USER_DIR / "exports")))
DB_PATH = Path(os.environ.get("RUSSO_DB_PATH", str(USER_DIR / "data" / "progress.sqlite3")))
DICTIONARY_PATH = DATA_DIR / "openrussian.sqlite3"
LEXICAL_MINIMUM_PATH = DATA_DIR / "lexical_minimum.sqlite3"
COURSE_LEXICON_PATH = DATA_DIR / "course_lexicon.json"
TTS_CACHE_DIR = USER_DIR / "data" / "tts_cache"

COURSES = [
    {"id": "russian", "name": "Russo", "native_name": "Русский", "level": "ТРКИ-II · B2", "mark": "Я", "available": True},
    {"id": "kazakh", "name": "Cazaque", "native_name": "Қазақ тілі", "level": "Em preparação", "mark": "Қ", "available": False},
    {"id": "romanian", "name": "Romeno", "native_name": "Română", "level": "CEFR · A1", "mark": "Ă", "available": True},
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).isoformat(timespec="seconds")


def session_exercises(items: list[dict], publicizer) -> list[dict]:
    """Prepara alternativas sem expor o gabarito e equilibra sua posição.

    Um simples ``shuffle`` independente pode, por acaso, pôr várias respostas
    seguidas na mesma coluna. Aqui cada bloco de N questões usa todas as N
    posições em ordem aleatória antes de repetir uma delas. Os distratores
    também são embaralhados, portanto não há uma sequência fixa para decorar.
    """
    position_bags: dict[int, list[int]] = {}
    last_positions: dict[int, int] = {}
    prepared: list[dict] = []

    for original in items:
        exercise = dict(original)
        options = list(exercise.get("options") or [])
        answer = exercise.get("answer")
        objective = exercise.get("type") in {"choice", "reading", "listening", "dialogue"}
        if objective and len(options) > 1 and answer in options:
            size = len(options)
            bag = position_bags.get(size, [])
            if not bag:
                bag = list(range(size))
                random.shuffle(bag)
                previous = last_positions.get(size)
                if previous is not None and bag[-1] == previous:
                    swap_index = 0 if bag[0] != previous else 1
                    bag[-1], bag[swap_index] = bag[swap_index], bag[-1]
                position_bags[size] = bag
            target = bag.pop()
            last_positions[size] = target
            distractors = [option for option in options if option != answer]
            random.shuffle(distractors)
            distractors.insert(target, answer)
            exercise["options"] = distractors
        prepared.append(publicizer(exercise))
    return prepared


SPOKEN_REPLACEMENTS = [
    (r"«([^»]*)»", r"\1"),
    (r"[“”\"]", ""),
    (r"\s*→\s*", " vira "),
    (r"\s*×\s*", " contra "),
    (r"\s*↔\s*", " e "),
    (r"\s*—\s*", ", "),
    (r"\s*–\s*", ", "),
    (r"(?<=[а-яёА-ЯЁa-zA-Z])\s*/\s*(?=[а-яёА-ЯЁa-zA-Z-])", " ou "),
    (r"\(([^()]{1,60})\)", r", \1,"),
    (r"\bTRKI[- ]?II\b", "Térki dois"),
    (r"\bТРКИ[- ]?II\b", "Térki dois"),
    (r"\bB2\b", "bê dois"),
    (r"\bB1\b", "bê um"),
    (r"\bA1\b", "á um"),
    (r"\bA2\b", "á dois"),
    (r"\bPT\b", "português"),
    (r"\bRU\b", "russo"),
    (r"(?<![\wа-яёА-ЯЁ])-(?=[а-яёА-ЯЁ])", ""),
    (r"\s*;\s*", ". "),
    (r"\s*:\s*", ", "),
    (r"\s*\.{3,}\s*", ". "),
    (r"\s{2,}", " "),
    (r"\s+([,.!?])", r"\1"),
    (r"([,.])\s*([,.])+", r"\1"),
]


def spoken_text(text: str) -> str:
    """Adapta um texto escrito para leitura em voz alta.

    Setas, barras, aspas tipográficas e abreviações de nível viram palavras
    faladas; travessões viram pausas curtas. Sem isso a voz lê "-ому/-ему"
    como uma sequência ininteligível de símbolos.
    """
    result = str(text or "")
    for pattern, replacement in SPOKEN_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)
    return result.strip()


def lesson_script(unit: dict, block_index: int | None = None) -> str:
    """Monta o roteiro falado da explicação de gramática de uma unidade.

    Cada bloco de ``grammar`` pode trazer ``audio_script`` — a versão escrita
    para o ouvido, com exemplos lidos por extenso. Sem esse campo, o roteiro
    cai para o texto escrito (título + parágrafos + exemplos), que continua
    inteligível depois de passar por ``spoken_text``.
    """
    blocks = unit.get("grammar") or []
    if block_index is not None:
        if block_index < 0 or block_index >= len(blocks):
            raise ValueError("Bloco de gramática inexistente nesta unidade.")
        selected = [blocks[block_index]]
        parts: list[str] = []
    else:
        selected = blocks
        parts = [f"Unidade: {unit.get('title', '')}."]
        if unit.get("description"):
            parts.append(str(unit["description"]))
    if not selected:
        raise ValueError("Esta unidade ainda não tem explicação de gramática.")
    for block in selected:
        script = block.get("audio_script")
        if script:
            parts.append(str(script))
            continue
        if block.get("title"):
            parts.append(f"{block['title']}.")
        parts.extend(str(paragraph) for paragraph in block.get("paragraphs", []))
        for example in block.get("examples", []):
            russian = example.get("ru", "")
            portuguese = example.get("pt", "")
            if russian:
                parts.append(f"Exemplo: {russian}. Em português: {portuguese}.")
    return " ".join(part.strip() for part in parts if str(part).strip())


def normalize_answer(value: object) -> str:
    """Normalização tolerante a caixa, espaços, ё/е e pontuação final."""
    text = unicodedata.normalize("NFC", str(value or "")).strip().lower()
    text = text.replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[.!?…]+$", "", text).strip()
    return text


def edit_distance(left: str, right: str) -> int:
    """Distância de Levenshtein com memória linear."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for index_left, char_left in enumerate(left, 1):
        current = [index_left]
        for index_right, char_right in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[index_right] + 1,
                previous[index_right - 1] + (char_left != char_right),
            ))
        previous = current
    return previous[-1]


def partial_score(answer: str, expected: str) -> tuple[float, str, str]:
    """Calcula crédito parcial sem aceitar uma regência trocada como correta."""
    given = normalize_answer(answer)
    target = normalize_answer(expected)
    if given == target:
        return 1.0, "correct", "Resposta exata."
    if not given or not target:
        return 0.0, "wrong", "Resposta ausente ou incompatível."

    given_tokens = given.split()
    target_tokens = target.split()
    critical = {"к", "от", "с", "в", "на", "за", "из", "по", "для"}
    critical_given = [token for token in given_tokens if token in critical]
    critical_target = [token for token in target_tokens if token in critical]
    regency_changed = critical_given != critical_target
    ratio = difflib.SequenceMatcher(None, given, target).ratio()
    distance = edit_distance(given, target)

    if len(target_tokens) == 1 and len(target) <= 3:
        return 0.0, "wrong", "Em respostas curtas, outra preposição muda a regência."
    if regency_changed and ratio >= 0.62:
        return 0.5, "partial", "A maior parte está reconhecível, mas a preposição/regência mudou."
    if distance == 1 and ratio >= 0.88:
        return 0.85, "minor_error", "Há apenas um provável erro pequeno de digitação ou ortografia."
    if ratio >= 0.90:
        return 0.75, "partial", "A construção está próxima, mas há um provável erro de forma ou terminação."
    if ratio >= 0.78:
        return 0.65, "partial", "A estrutura principal está próxima; revise formas ou terminações."
    if ratio >= 0.62:
        return 0.4, "partial", "Há elementos corretos, mas a resposta ainda precisa de revisão importante."
    return 0.0, "wrong", "A resposta diverge da construção esperada."


def mastery_having_sql() -> str:
    """HAVING que marca um exercício como dominado por qualquer patamar de MASTERY_TIERS."""
    clauses = [
        f"SUM(CASE WHEN COALESCE(score, is_correct) >= {min_score} THEN 1 ELSE 0 END) >= {min_count}"
        for min_score, min_count in MASTERY_TIERS
    ]
    return " OR ".join(clauses)


class ContentStore:
    def __init__(self, units_dir: Path):
        self.units_dir = units_dir
        self.units: list[dict] = []
        self.units_by_id: dict[str, dict] = {}
        self.exercises: dict[str, dict] = {}
        self.exercise_unit: dict[str, dict] = {}
        self.prefix_module: dict = {}
        self.vocab = VocabLessonStore(VOCAB_LESSONS_DIR)
        self.load()

    def load(self) -> None:
        units: list[dict] = []
        exercises: dict[str, dict] = {}
        exercise_unit: dict[str, dict] = {}
        for path in sorted(self.units_dir.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                unit = json.load(handle)
            unit.setdefault("course_id", "russian")
            required = {"id", "title", "exercises"}
            missing = required - unit.keys()
            if missing:
                raise ValueError(f"{path.name}: campos ausentes: {sorted(missing)}")
            for exercise in unit["exercises"]:
                ex_id = exercise.get("id")
                if not ex_id:
                    raise ValueError(f"{path.name}: exercício sem id")
                if ex_id in exercises:
                    raise ValueError(f"ID de exercício duplicado: {ex_id}")
                exercise.setdefault("tags", [])
                exercise.setdefault("difficulty", 1)
                exercise.setdefault("stage", "practice")
                exercise["unit_id"] = unit["id"]
                if exercise.get("type") == "match_pairs":
                    pairs = exercise.get("pairs", [])
                    exercise["left_items"] = [pair["left"] for pair in pairs]
                    shuffled_right = [pair["right"] for pair in pairs]
                    random.shuffle(shuffled_right)
                    exercise["right_items"] = shuffled_right
                exercises[ex_id] = exercise
                exercise_unit[ex_id] = unit
            units.append(unit)
        self.units = sorted(units, key=lambda item: item.get("order", 999))
        self.units_by_id = {unit["id"]: unit for unit in self.units}
        self.prefix_module = self._load_prefix_module(exercises, exercise_unit)
        self.vocab.load()
        for ex_id, exercise in self.vocab.exercises.items():
            if ex_id in exercises:
                raise ValueError(f"ID de exercício duplicado: {ex_id}")
            exercises[ex_id] = exercise
            exercise_unit[ex_id] = self.vocab.exercise_unit[ex_id]
        self.exercises = exercises
        self.exercise_unit = exercise_unit

    def _load_prefix_module(self, exercises: dict, exercise_unit: dict) -> dict:
        """Módulo autônomo de verbos com prefixo (página "Prefixos", só russo).

        Não entra em self.units: fica fora da trilha "Estudar" e da cadeia de
        travamento. Os exercícios, porém, entram em self.exercises para que
        /api/answer, a revisão espaçada e o histórico funcionem normalmente.
        """
        if not PREFIX_VERBS_PATH.exists():
            return {}
        with PREFIX_VERBS_PATH.open(encoding="utf-8") as handle:
            module = json.load(handle)
        module.setdefault("id", PREFIX_VERBS_UNIT_ID)
        module.setdefault("course_id", "russian")
        synthetic_unit = {
            "id": module["id"],
            "title": module.get("title", "Verbos com prefixo"),
            "course_id": module.get("course_id", "russian"),
            "exercises": module.get("exercises", []),
        }
        stage_ids = {stage["id"] for stage in module.get("stages", [])}
        for exercise in module.get("exercises", []):
            ex_id = exercise.get("id")
            if not ex_id:
                raise ValueError("prefix_verbs.json: exercício sem id")
            if ex_id in exercises:
                raise ValueError(f"ID de exercício duplicado: {ex_id}")
            if exercise.get("stage") not in stage_ids:
                raise ValueError(f"prefix_verbs.json: {ex_id} referencia stage inexistente")
            exercise.setdefault("tags", [])
            exercise.setdefault("difficulty", 1)
            exercise["unit_id"] = module["id"]
            exercises[ex_id] = exercise
            exercise_unit[ex_id] = synthetic_unit
        counts: dict[str, int] = {}
        for exercise in module.get("exercises", []):
            counts[exercise["stage"]] = counts.get(exercise["stage"], 0) + 1
        module["stage_counts"] = counts
        return module

    def public_unit(self, unit: dict) -> dict:
        return {
            key: value
            for key, value in unit.items()
            if key != "exercises"
        } | {"exercise_count": len(unit["exercises"])}

    def public_exercise(self, exercise: dict) -> dict:
        hidden = {
            "answer",
            "valid_answers",
            "back",
            "explanation",
            "feedback",
            "review_notes",
            "pairs",
            "after_audio",
        }
        return {key: value for key, value in exercise.items() if key not in hidden}

    def module_unit_ids(self, course_id: str) -> set[str]:
        """IDs internos dos módulos fora da trilha (Prefixos, Terminações, Vocabulário)."""
        if course_id not in ("", "russian"):
            return set()
        ids = {"lexical_minimum_morphology", "lexical_minimum_vocabulary", PREFIX_VERBS_UNIT_ID}
        ids.update(lesson["unit_key"] for lesson in self.vocab.lessons)
        return ids

    def course_unit_ids(self, course_id: str) -> set[str]:
        ids = {unit["id"] for unit in self.units if unit.get("course_id", "russian") == course_id}
        return ids | self.module_unit_ids(course_id)

    def reveal(self, exercise: dict) -> dict:
        answer = exercise.get("answer")
        if not answer:
            answers = exercise.get("valid_answers", [])
            answer = answers[0] if answers else exercise.get("back", "")
        return {
            "answer": answer,
            "back": exercise.get("back", answer),
            "explanation": exercise.get("explanation", ""),
            "feedback": exercise.get("feedback", ""),
        }


class LexicalMinimumStore:
    """Inventário TRKI-II e exercícios gerados a partir das formas do OpenRussian."""

    def __init__(self, path: Path):
        self.path = path
        self._vocab_pool: list[tuple[str, str, str]] | None = None
        self._vocab_options: dict[str, list[str]] = {}

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    STOPWORDS_EN = {"to", "the", "a", "an", "of", "be", "in", "on", "with", "for", "and", "or", "one's", "oneself", "sb", "sth", "at", "by"}

    @classmethod
    def _meaning_words(cls, translation: str) -> set[str]:
        words = re.findall(r"[a-z']+", (translation or "").lower())
        return {word for word in words if word not in cls.STOPWORDS_EN and len(word) > 2}

    def _vocabulary_options(self, conn: sqlite3.Connection, row: sqlite3.Row) -> list[str]:
        """Distratores da mesma classe e com final parecido, sem sinônimos.

        O inventário original sorteava distratores ao acaso: «блины» aparecia
        contra «недавно, никогда, шестнадцать», e a classe gramatical entregava
        a resposta. Aqui os candidatos têm a mesma classe (ou, sem classe, o
        mesmo final), comprimento próximo e raiz diferente; palavras cuja
        tradução inglesa compartilha um termo com a resposta são descartadas
        para não criar duas alternativas corretas. A escolha é determinística
        por cartão, para que a revisão espaçada mostre o mesmo conjunto.
        """
        cached = self._vocab_options.get(row["id"])
        if cached:
            return cached
        if self._vocab_pool is None:
            self._vocab_pool = [
                (item["display_lemma"], item["translation_en"] or "", item["parts_of_speech"] or "")
                for item in conn.execute("SELECT display_lemma, translation_en, parts_of_speech FROM vocabulary_cards")
            ]
        answer = row["display_lemma"]
        answer_pos = set(filter(None, (row["parts_of_speech"] or "").split(",")))
        answer_words = self._meaning_words(row["translation_en"])
        rng = random.Random(row["id"])

        def score(candidate: str, pos: str) -> float:
            value = 0.0
            if answer_pos and answer_pos & set(filter(None, pos.split(","))):
                value += 4
            if candidate[-3:] == answer[-3:]:
                value += 3
            elif candidate[-2:] == answer[-2:]:
                value += 2
            elif candidate[-1:] == answer[-1:]:
                value += 1
            value -= min(3, abs(len(candidate) - len(answer)) / 2)
            if (" " in candidate) != (" " in answer):
                value -= 3
            return value + rng.random()

        candidates = []
        for candidate, translation, pos in self._vocab_pool:
            if candidate == answer or candidate[:4] == answer[:4]:
                continue
            if answer_words & self._meaning_words(translation):
                continue
            candidates.append((score(candidate, pos), candidate))
        candidates.sort(reverse=True)
        top = [candidate for _, candidate in candidates[:10]]
        rng.shuffle(top)
        options = [answer] + top[:3]
        self._vocab_options[row["id"]] = options
        return options

    def metadata(self) -> dict[str, object]:
        if not self.path.exists():
            return {"available": False}
        with self.connect() as conn:
            values = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM metadata")}
        for key in ("parsed_entries", "unique_lemmas", "matched_entries", "morphology_lemmas", "morphology_cards", "vocabulary_cards"):
            if key in values:
                values[key] = int(values[key])
        values["available"] = True
        return values

    @staticmethod
    def public_exercise(exercise: dict) -> dict:
        hidden = {"answer", "valid_answers", "explanation", "feedback"}
        return {key: value for key, value in exercise.items() if key not in hidden}

    def exercise(self, exercise_id: str) -> dict | None:
        if not self.path.exists() or not (exercise_id.startswith("lm-") or exercise_id.startswith("lv-")):
            return None
        with self.connect() as conn:
            if exercise_id.startswith("lm-"):
                row = conn.execute("SELECT * FROM morphology_cards WHERE id = ?", (exercise_id,)).fetchone()
                return self._morphology_exercise(row) if row else None
            row = conn.execute("SELECT * FROM vocabulary_cards WHERE id = ?", (exercise_id,)).fetchone()
            return self._vocabulary_exercise(row, self._vocabulary_options(conn, row)) if row else None

    def questions(
        self,
        kind: str,
        limit: int,
        pos: str = "",
        case_code: str = "",
        number_code: str = "",
        excluded_lemmas: set[str] | None = None,
    ) -> list[dict]:
        if not self.path.exists():
            return []
        excluded = excluded_lemmas or set()
        limit = max(1, min(limit, 100))
        with self.connect() as conn:
            if kind == "vocabulary":
                sql = "SELECT * FROM vocabulary_cards WHERE 1=1"
                args: list[str] = []
                if pos:
                    sql += " AND (',' || parts_of_speech || ',') LIKE ?"
                    args.append(f"%,{pos},%")
                rows = list(conn.execute(sql, args))
                random.shuffle(rows)
                selected = [row for row in rows if row["lemma"] not in excluded][:limit]
                return [self._vocabulary_exercise(row, self._vocabulary_options(conn, row)) for row in selected]

            sql = "SELECT * FROM morphology_cards WHERE 1=1"
            args = []
            if pos:
                sql += " AND pos = ?"
                args.append(pos)
            if case_code:
                sql += " AND case_code = ?"
                args.append(case_code)
            if number_code:
                sql += " AND number_code = ?"
                args.append(number_code)
            rows = list(conn.execute(sql, args))
            random.shuffle(rows)
            selected: list[sqlite3.Row] = []
            used_lemmas: set[str] = set()
            for row in rows:
                if row["lemma"] in excluded or row["lemma"] in used_lemmas:
                    continue
                selected.append(row)
                used_lemmas.add(row["lemma"])
                if len(selected) >= limit:
                    break
            return [self._morphology_exercise(row) for row in selected]

    @staticmethod
    def _morphology_exercise(row: sqlite3.Row) -> dict:
        target = f"{row['number_ru']}"
        if row["target_gender"]:
            target += f", {row['target_gender']}"
        label = "substantivo" if row["pos"] == "noun" else "adjetivo"
        explanation = (
            f"{row['display_lemma']} → {row['answer']}: base «{row['stem']}» + "
            f"terminação «{row['ending']}». {row['case_ru']}, {target}. "
            f"Fonte lexical: página {row['source_page']} do Лексический минимум ТРКИ-II."
        )
        return {
            "id": row["id"],
            "unit_id": "lexical_minimum_morphology",
            "type": "choice",
            "stage": "practice",
            "difficulty": 2,
            "instruction": f"Escolha a flexão correta deste {label}.",
            "prompt": f"Qual é a forma de «{row['display_lemma']}» em {row['case_ru']} ({target})?",
            "options": json.loads(row["options_json"]),
            "answer": row["answer"],
            "explanation": explanation,
            "tags": [
                f"lexeme:{row['lemma']}", "Лексический минимум TRKI-II", "terminações",
                row["pos"], row["case_ru"], row["number_ru"],
            ],
            "lemma": row["lemma"],
            "display_lemma": row["display_lemma"],
            "translation_en": row["translation_en"] or "",
            "stem": row["stem"],
            "ending": row["ending"],
            "case_code": row["case_code"],
            "case_ru": row["case_ru"],
            "number_code": row["number_code"],
            "source_page": row["source_page"],
        }

    @staticmethod
    def _vocabulary_exercise(row: sqlite3.Row, options: list[str]) -> dict:
        return {
            "id": row["id"],
            "unit_id": "lexical_minimum_vocabulary",
            "type": "choice",
            "stage": "recognition",
            "difficulty": 2,
            "instruction": "Escolha a palavra russa correspondente ao significado em inglês.",
            "prompt": f"Qual palavra russa corresponde a “{row['translation_en']}”?",
            "options": options,
            "answer": row["display_lemma"],
            "explanation": (
                f"{row['display_lemma']} — {row['translation_en']}. "
                f"Fonte lexical: página {row['source_page']} do Лексический минимум ТРКИ-II."
            ),
            "tags": [f"lexeme:{row['lemma']}", "Лексический минимум TRKI-II", "vocabulário B2"],
            "lemma": row["lemma"],
            "display_lemma": row["display_lemma"],
            "translation_en": row["translation_en"],
            "source_page": row["source_page"],
        }
class DictionaryStore:
    """Consulta formas flexionadas no índice local do OpenRussian."""

    POS_LABELS = {
        "noun": "substantivo",
        "adjective": "adjetivo",
        "verb": "verbo",
        "other": "outra classe",
    }

    def __init__(self, path: Path, lexicon_path: Path):
        self.path = path
        self.course_lexicon = json.loads(lexicon_path.read_text(encoding="utf-8")) if lexicon_path.exists() else {}

    @staticmethod
    def normalize_word(value: str) -> str:
        text = unicodedata.normalize("NFC", value).lower().replace("ё", "е")
        text = text.replace("'", "").replace("´", "").replace("*", "")
        return re.sub(r"[^а-я-]", "", text)

    def lookup(self, word: str) -> dict:
        form = self.normalize_word(word)
        if not form or not self.path.exists():
            return {"word": word, "entries": [], "available": self.path.exists()}
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT e.lemma, e.accented, e.pos, e.translations_en,
                       e.gender, e.aspect, e.partner,
                       GROUP_CONCAT(f.grammar, ' · ') AS grammar
                FROM form_index f
                JOIN entries e ON e.id = f.entry_id
                WHERE f.form = ?
                GROUP BY e.id
                ORDER BY CASE WHEN e.lemma = ? THEN 0 ELSE 1 END, e.id
                LIMIT 8
                """,
                (form, form),
            ).fetchall()
        finally:
            conn.close()

        entries = []
        for row in rows:
            course = self.course_lexicon.get(row["lemma"], {})
            entries.append({
                "lemma": row["lemma"],
                "accented": row["accented"] or row["lemma"],
                "pos": self.POS_LABELS.get(row["pos"], row["pos"]),
                "translation_pt": course.get("translation_pt", ""),
                "translation_en": row["translations_en"] or "",
                "grammar": row["grammar"] or "",
                "gender": row["gender"] or "",
                "aspect": row["aspect"] or "",
                "partner": row["partner"] or "",
                "regency": course.get("regency", ""),
                "case": course.get("case", ""),
            })
        return {
            "word": word,
            "normalized": form,
            "available": True,
            "entries": entries,
            "source": "OpenRussian (CC BY-SA 4.0) + glossário português do curso",
        }


class TTSService:
    """Gera MP3 com edge-tts e mantém cache por texto/voz.

    Dois modos:

    - ``target``  → voz nativa do idioma estudado, ritmo lento (-12%), textos
      curtos (frases de exercício, alternativas, palavras do dicionário);
    - ``lesson``  → voz multilíngue em português do Brasil, ritmo levemente
      reduzido (-6%), textos longos (a explicação de gramática da unidade).
      A voz multilíngue pronuncia os exemplos em russo dentro da narração em
      português sem trocar de motor, que é o que torna possível uma "aula
      falada" com exemplos reais.
    """

    VOICES = {
        "russian": "ru-RU-SvetlanaNeural",
        "romanian": "ro-RO-AlinaNeural",
        "kazakh": "kk-KZ-AigulNeural",
    }
    LESSON_VOICE = "pt-BR-ThalitaMultilingualNeural"
    LESSON_MAX_CHARS = 7000
    # Vozes dos diálogos russos. Só há duas vozes neurais russas no edge-tts;
    # a terceira e a quarta pessoa usam a mesma voz com outro tom, o que basta
    # para o ouvido separar os falantes numa cena.
    DIALOGUE_VOICES = {
        "f": ("ru-RU-SvetlanaNeural", "+0Hz"),
        "m": ("ru-RU-DmitryNeural", "+0Hz"),
        "f2": ("ru-RU-SvetlanaNeural", "-14Hz"),
        "m2": ("ru-RU-DmitryNeural", "+12Hz"),
    }
    DIALOGUE_RATE = "-6%"

    EDGE_RETRY_SECONDS = 300

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._edge_down_until = 0.0

    def audio_for(self, text: str, course_id: str = "russian", mode: str = "target", speaker: str = "") -> Path:
        cleaned = re.sub(r"\s+", " ", text).strip()
        pitch = "+0Hz"
        if mode == "lesson":
            voice, rate, limit = self.LESSON_VOICE, "-6%", self.LESSON_MAX_CHARS
            cleaned = spoken_text(cleaned)
        elif speaker and course_id == "russian":
            if speaker not in self.DIALOGUE_VOICES:
                raise ValueError("Voz de diálogo desconhecida.")
            voice, pitch = self.DIALOGUE_VOICES[speaker]
            rate, limit = self.DIALOGUE_RATE, 800
        else:
            voice = self.VOICES.get(course_id)
            rate, limit = "-12%", 800
        if not voice:
            raise ValueError("Curso sem voz TTS configurada.")
        if not cleaned or len(cleaned) > limit or not re.search(r"[A-Za-zÀ-žА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]", cleaned):
            raise ValueError(f"O texto de áudio deve conter texto legível e ter até {limit} caracteres.")
        # O tom só entra na chave quando difere do padrão: o cache antigo continua válido.
        key = f"{voice}|{rate}|{cleaned}" if pitch == "+0Hz" else f"{voice}|{rate}|{pitch}|{cleaned}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        target = self.cache_dir / f"{digest}.mp3"
        if target.exists() and target.stat().st_size > 0:
            return target
        offline_ok = mode != "lesson" and voice.startswith("ru-") and sys.platform == "win32"
        if edge_tts is None or (offline_ok and time.monotonic() < self._edge_down_until):
            if offline_ok:
                return self._offline_audio(cleaned)
            raise RuntimeError("edge-tts não está instalado; execute o aplicativo pelo run.sh.")
        temporary = target.with_suffix(f".{secrets.token_hex(6)}.tmp")
        with self._lock:
            if target.exists() and target.stat().st_size > 0:
                return target
            communicate = edge_tts.Communicate(cleaned, voice, rate=rate, pitch=pitch)
            try:
                communicate.save_sync(str(temporary))
                temporary.replace(target)
                self._edge_down_until = 0.0
            except Exception:
                # A Microsoft já recusou conexões do edge-tts de uma hora para outra (erro 403).
                # Em vez de falhar, o russo cai na voz offline do Windows e o Edge fica de lado por um tempo.
                if not offline_ok:
                    raise
                self._edge_down_until = time.monotonic() + self.EDGE_RETRY_SECONDS
                return self._offline_audio(cleaned)
            finally:
                temporary.unlink(missing_ok=True)
        return target

    def _offline_audio(self, text: str) -> Path:
        """Voz russa instalada no Windows (SAPI). Fica em pasta própria para nunca se misturar ao cache do Edge."""
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
                env=env, capture_output=True, timeout=30, creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            if result.returncode == 3:
                raise RuntimeError("O Windows não tem uma voz em russo instalada (Configurações > Hora e idioma > Fala).")
            if result.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
                raise RuntimeError("A voz offline do Windows falhou.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target


class Database:
    def __init__(self, path: Path, content: ContentStore, lexical: LexicalMinimumStore):
        self.path = path
        self.content = content
        self.lexical = lexical
        self._lock = threading.Lock()
        self.sessions = SessionStore(self.connect, self._lock)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    exercise_id TEXT NOT NULL,
                    exercise_type TEXT NOT NULL,
                    stage TEXT,
                    mode TEXT NOT NULL,
                    consultation TEXT NOT NULL,
                    prompt_snapshot TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    expected_snapshot TEXT,
                    is_correct INTEGER,
                    response_ms INTEGER,
                    self_error_type TEXT,
                    tags_json TEXT NOT NULL,
                    app_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS progress (
                    exercise_id TEXT PRIMARY KEY,
                    repetitions INTEGER NOT NULL DEFAULT 0,
                    interval_days REAL NOT NULL DEFAULT 0,
                    ease REAL NOT NULL DEFAULT 2.5,
                    due_at TEXT NOT NULL,
                    lapses INTEGER NOT NULL DEFAULT 0,
                    last_result INTEGER,
                    last_consultation TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS content_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    exercise_id TEXT NOT NULL,
                    prompt_snapshot TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    note TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    context_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lexeme_progress (
                    lemma TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    exposures INTEGER NOT NULL DEFAULT 0,
                    best_score REAL NOT NULL DEFAULT 0,
                    exact_sc INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS unit_completion (
                    unit_id TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_attempts_exercise
                    ON attempts(exercise_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_attempts_unit
                    ON attempts(unit_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_progress_due
                    ON progress(due_at);
                CREATE INDEX IF NOT EXISTS idx_content_reports_status
                    ON content_reports(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_lexeme_progress_mastery
                    ON lexeme_progress(exact_sc, last_seen);
                """
            )
            self._ensure_column(conn, "attempts", "score", "REAL")
            self._ensure_column(conn, "attempts", "verdict", "TEXT")
            SessionStore.init_schema(conn)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def save_attempt(self, payload: dict, exercise: dict, result: dict) -> int:
        prompt = exercise.get("prompt") or exercise.get("front") or exercise.get("question", "")
        answer_text = payload.get("answer", "")
        if isinstance(answer_text, list):
            if answer_text and all(isinstance(item, dict) for item in answer_text):
                answer_text = "; ".join(f"{item.get('left', '')} = {item.get('right', '')}" for item in answer_text)
            else:
                answer_text = " ".join(str(item) for item in answer_text)
        expected = result.get("correct_answer")
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO attempts (
                    created_at, session_id, unit_id, exercise_id, exercise_type,
                    stage, mode, consultation, prompt_snapshot, answer_text,
                    expected_snapshot, is_correct, response_ms, self_error_type,
                    tags_json, app_version, score, verdict
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    iso(),
                    str(payload.get("session_id") or "sem-sessao"),
                    exercise["unit_id"],
                    exercise["id"],
                    exercise.get("type", "unknown"),
                    exercise.get("stage", "practice"),
                    str(payload.get("mode") or "study"),
                    str(payload.get("consultation") or "SC"),
                    prompt,
                    str(answer_text),
                    expected,
                    None if result["is_correct"] is None else int(result["is_correct"]),
                    max(0, int(payload.get("response_ms") or 0)),
                    json.dumps(exercise.get("tags", []), ensure_ascii=False),
                    APP_VERSION,
                    result.get("score"),
                    result.get("verdict"),
                ),
            )
            attempt_id = int(cursor.lastrowid)
            if result["is_correct"] is not None:
                self._update_progress(
                    conn,
                    exercise["id"],
                    float(result.get("score") or 0),
                    str(payload.get("consultation") or "SC"),
                    payload.get("rating"),
                )
                self._update_lexeme_progress(
                    conn,
                    exercise.get("tags", []),
                    float(result.get("score") or 0),
                    str(payload.get("consultation") or "SC"),
                )
                self._maybe_complete_unit(conn, exercise["unit_id"])
            conn.commit()
        self.write_live_exports()
        return attempt_id

    @staticmethod
    def _update_lexeme_progress(
        conn: sqlite3.Connection,
        tags: list[str],
        score: float,
        consultation: str,
    ) -> None:
        lemmas = {tag.split(":", 1)[1] for tag in tags if tag.startswith("lexeme:") and ":" in tag}
        for lemma in lemmas:
            timestamp = iso()
            exact_increment = int(score >= 1 and consultation == "SC")
            conn.execute(
                """
                INSERT INTO lexeme_progress (
                    lemma, first_seen, last_seen, exposures, best_score, exact_sc
                ) VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(lemma) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    exposures=lexeme_progress.exposures + 1,
                    best_score=MAX(lexeme_progress.best_score, excluded.best_score),
                    exact_sc=lexeme_progress.exact_sc + excluded.exact_sc
                """,
                (lemma, timestamp, timestamp, score, exact_increment),
            )

    def lexeme_seen(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT lemma FROM lexeme_progress").fetchall()
        return {row["lemma"] for row in rows}

    def lexical_coverage(self) -> dict[str, object]:
        metadata = self.lexical.metadata()
        total = int(metadata.get("unique_lemmas", 0))
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS seen,
                       SUM(CASE WHEN exact_sc >= 2 THEN 1 ELSE 0 END) AS mastered,
                       SUM(exposures) AS exposures
                FROM lexeme_progress
                """
            ).fetchone()
        seen = int(row["seen"] or 0)
        mastered = int(row["mastered"] or 0)
        return {
            "total": total,
            "seen": seen,
            "mastered": mastered,
            "exposures": int(row["exposures"] or 0),
            "seen_percent": round(100 * seen / total, 2) if total else 0,
            "mastered_percent": round(100 * mastered / total, 2) if total else 0,
            "mastery_rule": "2 acertos exatos sem consulta",
        }

    def _update_progress(
        self,
        conn: sqlite3.Connection,
        exercise_id: str,
        score: float,
        consultation: str,
        rating: object,
    ) -> None:
        row = conn.execute(
            "SELECT * FROM progress WHERE exercise_id = ?", (exercise_id,)
        ).fetchone()
        repetitions = int(row["repetitions"]) if row else 0
        ease = float(row["ease"]) if row else 2.5
        lapses = int(row["lapses"]) if row else 0

        try:
            rating_value = int(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating_value = None

        if score <= 0:
            repetitions = 0
            lapses += 1
            ease = max(1.3, ease - 0.2)
            interval = 10 / (24 * 60)  # dez minutos
        elif score < 1:
            repetitions = 0
            ease = max(1.3, ease - 0.08)
            interval = 0.25  # seis horas: reconheceu parte, mas ainda não dominou
        else:
            repetitions += 1
            base_intervals = [1, 3, 7, 14, 30, 60, 120]
            interval = base_intervals[min(repetitions - 1, len(base_intervals) - 1)]
            if consultation == "C":
                interval = min(interval, 1)
                ease = max(1.3, ease - 0.08)
            elif consultation == "CC":
                interval = min(interval, 3)
            elif rating_value == 4:
                interval *= 1.5
                ease = min(3.0, ease + 0.08)
            elif rating_value == 2:
                interval = max(1, interval * 0.6)
                ease = max(1.3, ease - 0.05)

        due_at = now_utc() + timedelta(days=interval)
        conn.execute(
            """
            INSERT INTO progress (
                exercise_id, repetitions, interval_days, ease, due_at,
                lapses, last_result, last_consultation, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exercise_id) DO UPDATE SET
                repetitions=excluded.repetitions,
                interval_days=excluded.interval_days,
                ease=excluded.ease,
                due_at=excluded.due_at,
                lapses=excluded.lapses,
                last_result=excluded.last_result,
                last_consultation=excluded.last_consultation,
                updated_at=excluded.updated_at
            """,
            (
                exercise_id,
                repetitions,
                interval,
                ease,
                iso(due_at),
                lapses,
                score,
                consultation,
                iso(),
            ),
        )

    def _maybe_complete_unit(self, conn: sqlite3.Connection, unit_id: str) -> None:
        unit = self.content.units_by_id.get(unit_id)
        if not unit:
            return
        gradable_ids = [
            exercise["id"] for exercise in unit["exercises"] if exercise.get("type") != "open_text"
        ]
        if not gradable_ids:
            return
        already = conn.execute(
            "SELECT 1 FROM unit_completion WHERE unit_id = ?", (unit_id,)
        ).fetchone()
        if already:
            return
        placeholders = ",".join("?" for _ in gradable_ids)
        cleared = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM (
                SELECT exercise_id
                FROM attempts
                WHERE is_correct IS NOT NULL AND exercise_id IN ({placeholders})
                GROUP BY exercise_id
                HAVING {mastery_having_sql()}
            )
            """,
            gradable_ids,
        ).fetchone()["c"]
        if cleared / len(gradable_ids) >= UNIT_COMPLETION_THRESHOLD:
            conn.execute(
                "INSERT OR IGNORE INTO unit_completion (unit_id, completed_at) VALUES (?, ?)",
                (unit_id, iso()),
            )

    def reconcile_unit_completion(self) -> None:
        """Reaplica a regra de conclusão a todas as unidades.

        Necessário porque `_maybe_complete_unit` só roda ao salvar uma nova
        tentativa: sem isto, mudar MASTERY_TIERS/UNIT_COMPLETION_THRESHOLD não
        destrava quem já tinha nota suficiente sob a regra nova mas não
        respondeu mais nada desde então.
        """
        with self._lock, self.connect() as conn:
            for unit in self.content.units:
                self._maybe_complete_unit(conn, unit["id"])

    def unit_progress(self, course_id: str = "") -> list[dict]:
        with self.connect() as conn:
            completed_ids = {
                row["unit_id"] for row in conn.execute("SELECT unit_id FROM unit_completion")
            }
            # "Dominado" = domínio cumulativo (ver MASTERY_TIERS): nota alta numa
            # tentativa conta tanto quanto nota média repetida várias vezes. Um erro
            # isolado numa revisão espaçada posterior não faz o exercício "regredir"
            # e travar o desbloqueio da próxima unidade, pois olhamos o histórico
            # inteiro de tentativas, não só a última.
            cleared_ids = {
                row["exercise_id"]
                for row in conn.execute(
                    f"""
                    SELECT exercise_id
                    FROM attempts
                    WHERE is_correct IS NOT NULL
                    GROUP BY exercise_id
                    HAVING {mastery_having_sql()}
                    """
                )
            }
        result = []
        previous_completed: dict[str, bool] = defaultdict(lambda: True)
        units = [unit for unit in self.content.units if not course_id or unit.get("course_id") == course_id]
        for unit in units:
            unit_course = unit.get("course_id", "russian")
            # Unidades de order 0 (diagnóstico) ficam sempre disponíveis, fora da trilha
            # sequencial: não são bloqueadas nem servem de pré-requisito para as demais.
            standalone = unit.get("order", 999) == 0
            gradable = [ex for ex in unit["exercises"] if ex.get("type") != "open_text"]
            total = len(gradable)
            cleared = sum(1 for ex in gradable if ex["id"] in cleared_ids)
            completed = unit["id"] in completed_ids
            result.append({
                "unit_id": unit["id"],
                "total": total,
                "cleared": cleared,
                "percent": round(100 * cleared / total) if total else 100,
                "completed": completed,
                "unlocked": True if standalone else previous_completed[unit_course],
            })
            if not standalone:
                previous_completed[unit_course] = completed
        return result

    def prefix_progress(self) -> dict:
        """Domínio por prefixo no módulo "Verbos com prefixo".

        Mesma regra cumulativa de MASTERY_TIERS usada na trilha. Retorna
        {stage_id: {"total", "cleared"}} mais um total geral.
        """
        module = self.content.prefix_module
        exercises = module.get("exercises", [])
        if not exercises:
            return {"stages": {}, "total": 0, "cleared": 0}
        with self.connect() as conn:
            cleared_ids = {
                row["exercise_id"]
                for row in conn.execute(
                    f"""
                    SELECT exercise_id
                    FROM attempts
                    WHERE is_correct IS NOT NULL
                    GROUP BY exercise_id
                    HAVING {mastery_having_sql()}
                    """
                )
            }
        stages: dict[str, dict] = {}
        for exercise in exercises:
            bucket = stages.setdefault(exercise["stage"], {"total": 0, "cleared": 0})
            bucket["total"] += 1
            if exercise["id"] in cleared_ids:
                bucket["cleared"] += 1
        return {
            "stages": stages,
            "total": len(exercises),
            "cleared": sum(1 for ex in exercises if ex["id"] in cleared_ids),
        }

    def cleared_exercise_ids(self) -> set[str]:
        with self.connect() as conn:
            return {
                row["exercise_id"]
                for row in conn.execute(
                    f"""
                    SELECT exercise_id
                    FROM attempts
                    WHERE is_correct IS NOT NULL
                    GROUP BY exercise_id
                    HAVING {mastery_having_sql()}
                    """
                )
            }

    def vocab_progress(self) -> dict[str, dict]:
        """Domínio por lição de vocabulário (mesma regra cumulativa da trilha).

        Além dos exercícios, conta quantas das oito construções já estão
        firmes: uma construção conta quando suas tarefas de forma e de contexto
        (form, cloze, build) atingiram o patamar de domínio.
        """
        cleared = self.cleared_exercise_ids()
        with self.connect() as conn:
            attempted_ids = {
                row["exercise_id"]
                for row in conn.execute(
                    "SELECT DISTINCT exercise_id FROM attempts WHERE unit_id LIKE ?",
                    (VOCAB_UNIT_PREFIX + "%",),
                )
            }
        result: dict[str, dict] = {}
        for lesson in self.content.vocab.lessons:
            graded = [
                exercise["id"] for exercise in lesson["generated"]
                if exercise["type"] not in UNGRADED_TYPES and exercise["type"] != "open_text"
            ]
            items_firm = sum(
                1 for item in lesson["items"]
                if all(f"vx-{lesson['id']}-{item['key']}-{role}" in cleared for role in ("form", "cloze", "build"))
            )
            result[lesson["id"]] = {
                "total": len(graded),
                "cleared": sum(1 for ex_id in graded if ex_id in cleared),
                "attempted": sum(1 for ex_id in graded if ex_id in attempted_ids),
                "items_total": len(lesson["items"]),
                "items_firm": items_firm,
            }
        return result

    def classify_attempt(self, attempt_id: int, category: str) -> bool:
        allowed = {"regencia", "terminacao", "vocabulario", "aspecto", "gramatica", "ortografia", "pronuncia", "digitacao", "nao_sei"}
        if category not in allowed:
            return False
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE attempts SET self_error_type = ? WHERE id = ?",
                (category, attempt_id),
            )
            conn.commit()
        self.write_live_exports()
        return cursor.rowcount == 1

    def save_content_report(self, payload: dict, exercise: dict) -> int:
        prompt = exercise.get("prompt") or exercise.get("front") or ""
        reason = str(payload.get("reason") or "outro")[:80]
        note = str(payload.get("note") or "").strip()[:2000]
        context = {
            "exercise_type": exercise.get("type"),
            "stage": exercise.get("stage"),
            "answer_during_report": payload.get("answer", ""),
            "app_version": APP_VERSION,
        }
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO content_reports (
                    created_at, session_id, unit_id, exercise_id,
                    prompt_snapshot, reason, note, status, context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    iso(),
                    str(payload.get("session_id") or "sem-sessao"),
                    exercise["unit_id"],
                    exercise["id"],
                    prompt,
                    reason,
                    note,
                    json.dumps(context, ensure_ascii=False),
                ),
            )
            report_id = int(cursor.lastrowid)
            conn.commit()
        self.write_live_exports()
        return report_id

    def content_reports(self, status: str = "open", course_id: str = "") -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, session_id, unit_id, exercise_id,
                       prompt_snapshot, reason, note, status, context_json
                FROM content_reports
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                (status,),
            ).fetchall()
        reports = [dict(row) for row in rows]
        if course_id:
            allowed = self.content.course_unit_ids(course_id)
            reports = [report for report in reports if report["unit_id"] in allowed]
        return reports

    def due_ids(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT exercise_id FROM progress WHERE due_at <= ? ORDER BY due_at",
                (iso(),),
            ).fetchall()
        return [row["exercise_id"] for row in rows]

    def difficult_ids(self, limit: int = 30) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT exercise_id,
                       SUM(CASE WHEN COALESCE(score, is_correct) < 1 THEN 1 ELSE 0 END) AS errors,
                       COUNT(*) AS attempts
                FROM attempts
                WHERE is_correct IS NOT NULL
                GROUP BY exercise_id
                HAVING errors > 0
                ORDER BY CAST(errors AS REAL) / attempts DESC, errors DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row["exercise_id"] for row in rows]

    def pending_writing(self, course_id: str = "") -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, unit_id, exercise_id, prompt_snapshot,
                       answer_text, consultation, response_ms
                FROM attempts
                WHERE is_correct IS NULL
                ORDER BY created_at DESC
                """
            ).fetchall()
        items = [dict(row) for row in rows]
        if course_id:
            allowed = self.content.course_unit_ids(course_id)
            items = [item for item in items if item["unit_id"] in allowed]
        return items

    def summary(self, course_id: str = "") -> dict:
        with self.connect() as conn:
            attempts = conn.execute(
                "SELECT * FROM attempts ORDER BY created_at"
            ).fetchall()
            progress = conn.execute("SELECT * FROM progress").fetchall()

        if course_id:
            allowed_units = self.content.course_unit_ids(course_id)
            attempts = [row for row in attempts if row["unit_id"] in allowed_units]
            allowed_exercises = {
                exercise["id"] for exercise in self.content.exercises.values()
                if exercise.get("unit_id") in allowed_units
            }
            if course_id == "russian":
                progress = [row for row in progress if row["exercise_id"] in allowed_exercises or row["exercise_id"].startswith(("lm-", "lv-"))]
            else:
                progress = [row for row in progress if row["exercise_id"] in allowed_exercises]

        graded_rows = [row for row in attempts if row["is_correct"] is not None]
        total_graded = len(graded_rows)
        scores = [float(row["score"] if row["score"] is not None else row["is_correct"]) for row in graded_rows]
        correct = sum(score >= 1 for score in scores)
        partial = sum(0 < score < 1 for score in scores)
        sc_rows = [row for row in attempts if row["is_correct"] is not None and row["consultation"] == "SC"]
        sc_points = sum(float(row["score"] if row["score"] is not None else row["is_correct"]) for row in sc_rows)
        by_tag: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "correct": 0, "partial": 0, "points": 0.0, "weighted": 0.0})
        error_types: Counter[str] = Counter()
        by_unit: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "correct": 0, "partial": 0, "points": 0.0})
        recent_errors: list[dict] = []
        response_times: list[int] = []

        weights = {"SC": 1.0, "CC": 0.75, "C": 0.5}
        for row in attempts:
            if row["is_correct"] is not None:
                score = float(row["score"] if row["score"] is not None else row["is_correct"])
                by_unit[row["unit_id"]]["attempts"] += 1
                by_unit[row["unit_id"]]["correct"] += int(score >= 1)
                by_unit[row["unit_id"]]["partial"] += int(0 < score < 1)
                by_unit[row["unit_id"]]["points"] += score
                if row["response_ms"]:
                    response_times.append(int(row["response_ms"]))
            if row["self_error_type"]:
                error_types[row["self_error_type"]] += 1
            tags = json.loads(row["tags_json"] or "[]")
            for tag in tags:
                if row["is_correct"] is None:
                    continue
                score = float(row["score"] if row["score"] is not None else row["is_correct"])
                by_tag[tag]["attempts"] += 1
                by_tag[tag]["correct"] += int(score >= 1)
                by_tag[tag]["partial"] += int(0 < score < 1)
                by_tag[tag]["points"] += score
                by_tag[tag]["weighted"] += score * weights.get(row["consultation"], 1)
            if row["is_correct"] is not None and float(row["score"] if row["score"] is not None else row["is_correct"]) < 1:
                recent_errors.append({
                    "attempt_id": row["id"],
                    "created_at": row["created_at"],
                    "exercise_id": row["exercise_id"],
                    "prompt": row["prompt_snapshot"],
                    "answer": row["answer_text"],
                    "expected": row["expected_snapshot"],
                    "category": row["self_error_type"],
                    "score": row["score"] if row["score"] is not None else row["is_correct"],
                    "verdict": row["verdict"] or ("wrong" if row["is_correct"] == 0 else "correct"),
                })

        tag_stats = []
        for tag, values in by_tag.items():
            attempts_count = values["attempts"]
            tag_stats.append({
                "tag": tag,
                **values,
                "accuracy": round(100 * values["points"] / attempts_count) if attempts_count else None,
                "mastery": round(100 * values["weighted"] / attempts_count) if attempts_count else None,
            })
        tag_stats.sort(key=lambda item: (item["mastery"], item["tag"]))

        unit_stats = []
        unit_titles = {unit["id"]: unit["title"] for unit in self.content.units}
        if self.content.prefix_module:
            unit_titles[PREFIX_VERBS_UNIT_ID] = self.content.prefix_module.get("title", "Verbos com prefixo")
        for lesson in self.content.vocab.lessons:
            unit_titles[lesson["unit_key"]] = f"Vocabulário · {lesson['title']}"
        unit_titles.setdefault("lexical_minimum_morphology", "Terminações · flexão")
        unit_titles.setdefault("lexical_minimum_vocabulary", "Terminações · cobertura lexical")
        for unit_id, values in by_unit.items():
            count = values["attempts"]
            unit_stats.append({
                "unit_id": unit_id,
                "title": unit_titles.get(unit_id, unit_id),
                **values,
                "accuracy": round(100 * values["points"] / count) if count else None,
            })

        now_text = iso()
        due_count = sum(row["due_at"] <= now_text for row in progress)
        mature_count = sum(row["repetitions"] >= 4 for row in progress)
        return {
            "generated_at": iso(),
            "app_version": APP_VERSION,
            "total_attempts": len(attempts),
            "graded_attempts": total_graded,
            "correct": correct,
            "partial": partial,
            "accuracy": round(100 * sum(scores) / total_graded) if total_graded else None,
            "sc_attempts": len(sc_rows),
            "sc_accuracy": round(100 * sc_points / len(sc_rows)) if sc_rows else None,
            "due_count": due_count,
            "mature_count": mature_count,
            "tracked_cards": len(progress),
            "pending_writing": sum(row["is_correct"] is None for row in attempts),
            "open_reports": len(self.content_reports(course_id=course_id)),
            "median_response_ms": sorted(response_times)[len(response_times) // 2] if response_times else None,
            "by_tag": tag_stats,
            "by_unit": unit_stats,
            "error_types": dict(error_types),
            "recent_errors": list(reversed(recent_errors[-20:])),
            "lexical_coverage": self.lexical_coverage() if course_id in ("", "russian") else {},
            "unit_progress": self.unit_progress(course_id),
        }

    def all_attempts(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM attempts ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def write_live_exports(self) -> None:
        summary = self.summary()
        attempts = self.all_attempts()
        pending = self.pending_writing()
        reports = self.content_reports()

        (EXPORT_DIR / "analise_atual.json").write_text(
            json.dumps(
                {"summary": summary, "pending_writing": pending, "content_reports": reports, "attempts": attempts},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fields = [
            "id", "created_at", "session_id", "unit_id", "exercise_id",
            "exercise_type", "stage", "mode", "consultation", "prompt_snapshot",
            "answer_text", "expected_snapshot", "is_correct", "response_ms",
            "self_error_type", "tags_json", "app_version", "score", "verdict",
        ]
        with (EXPORT_DIR / "respostas.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(attempts)

        lines = [
            "# Relatório atual — Русский тренажёр",
            "",
            f"Gerado em: {summary['generated_at']}",
            f"Tentativas: {summary['total_attempts']}",
            f"Precisão geral: {summary['accuracy'] if summary['accuracy'] is not None else '—'}%",
            f"Precisão sem consulta: {summary['sc_accuracy'] if summary['sc_accuracy'] is not None else '—'}%",
            f"Revisões vencidas: {summary['due_count']}",
            f"Léxico TRKI-II visto: {summary['lexical_coverage']['seen']} / {summary['lexical_coverage']['total']} ({summary['lexical_coverage']['seen_percent']}%)",
            f"Léxico TRKI-II dominado: {summary['lexical_coverage']['mastered']} ({summary['lexical_coverage']['mastered_percent']}%)",
            f"Produções pendentes de correção: {summary['pending_writing']}",
            f"Problemas de conteúdo sinalizados: {summary['open_reports']}",
            "",
            "## Domínio por etiqueta",
            "",
        ]
        if summary["by_tag"]:
            for item in summary["by_tag"]:
                lines.append(
                    f"- {item['tag']}: domínio {item['mastery']}%, "
                    f"exatos {item['correct']}, parciais {item['partial']}, tentativas {item['attempts']}"
                )
        else:
            lines.append("Ainda não há respostas.")
        active_sessions = self.sessions.active()
        lines += ["", "## Sessões em andamento (podem ser retomadas)", ""]
        if active_sessions:
            for session in active_sessions:
                lines.append(
                    f"- {session['title']}: tela {min(session['resume_index'] + 1, session['total'])} de "
                    f"{session['total']}, {session['answered']} respostas, salva em {session['updated_at']}"
                )
        else:
            lines.append("Nenhuma sessão interrompida.")
        lines += ["", "## Erros recentes", ""]
        if summary["recent_errors"]:
            for item in summary["recent_errors"][:10]:
                lines += [
                    f"- **{item['exercise_id']}** — {item['prompt']}",
                    f"  - Resposta: {item['answer']}",
                    f"  - Esperado: {item['expected']}",
                    f"  - Categoria: {item['category'] or 'não classificado'}",
                    f"  - Crédito: {round(float(item['score']) * 100)}% ({item['verdict']})",
                ]
        else:
            lines.append("Ainda não há erros registrados.")
        (EXPORT_DIR / "relatorio_atual.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        report_lines = ["# Problemas de conteúdo sinalizados", ""]
        if reports:
            for report in reports:
                report_lines += [
                    f"## #{report['id']} · {report['exercise_id']}",
                    "",
                    f"- Data: {report['created_at']}",
                    f"- Unidade: {report['unit_id']}",
                    f"- Motivo: {report['reason']}",
                    f"- Enunciado: {report['prompt_snapshot']}",
                    f"- Observação: {report['note'] or 'sem observação'}",
                    "",
                ]
        else:
            report_lines.append("Nenhum problema aberto.")
        (EXPORT_DIR / "problemas_reportados.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def grade(exercise: dict, payload: dict) -> dict:
    exercise_type = exercise.get("type", "input")
    answer = payload.get("answer", "")

    if exercise_type in UNGRADED_TYPES:
        raise ValueError("Este cartão é de apresentação e não é corrigido.")

    if exercise_type == "open_text":
        text = str(answer).strip()
        return {
            "is_correct": None,
            "is_partial": False,
            "score": None,
            "verdict": "pending_review",
            "correct_answer": None,
            "message": "Produção salva para correção posterior.",
            "explanation": exercise.get("review_notes", ""),
            "word_count": len(re.findall(r"[\wА-Яа-яЁё-]+", text, flags=re.UNICODE)),
        }

    if exercise_type == "match_pairs":
        pairs = exercise.get("pairs", [])
        correct_map = {pair["left"]: pair["right"] for pair in pairs}
        total = len(correct_map) or 1
        given = answer if isinstance(answer, list) else []
        matched = 0
        seen_left: set[str] = set()
        for item in given:
            if not isinstance(item, dict):
                continue
            left = item.get("left")
            if left in seen_left:
                continue
            seen_left.add(left)
            if left in correct_map and correct_map[left] == item.get("right"):
                matched += 1
        score = matched / total
        correct = matched == total and len(given) == total
        verdict = "correct" if correct else "partial" if matched else "wrong"
        correct_answer = "; ".join(f"{pair['left']} — {pair['right']}" for pair in pairs)
        return {
            "is_correct": correct,
            "is_partial": 0 < score < 1,
            "score": score,
            "verdict": verdict,
            "correct_answer": correct_answer,
            "message": "Correto." if correct else "Quase." if score > 0 else "Ainda não.",
            "proximity_note": f"{matched}/{total} pares corretos.",
            "explanation": exercise.get("explanation", ""),
            "correct_pairs": [{"left": pair["left"], "right": pair["right"]} for pair in pairs],
        }

    if exercise_type == "flashcard":
        try:
            rating = int(payload.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        score = {1: 0.0, 2: 0.65, 3: 1.0, 4: 1.0}.get(rating, 0.0)
        correct = score >= 1
        return {
            "is_correct": correct,
            "is_partial": 0 < score < 1,
            "score": score,
            "verdict": "correct" if correct else "partial" if score else "wrong",
            "correct_answer": exercise.get("back") or exercise.get("answer", ""),
            "message": "Autoavaliação registrada.",
            "explanation": exercise.get("explanation", ""),
        }

    answer_text = " ".join(answer) if isinstance(answer, list) else str(answer)
    valid = list(exercise.get("valid_answers", []))
    if exercise.get("answer") is not None:
        valid.insert(0, str(exercise["answer"]))
    canonical = valid[0] if valid else ""
    # Um cartão de morfologia pode ser apresentado sem alternativas. Nesse
    # modo, um deslize de terminação recebe crédito parcial em vez de ser
    # tratado como uma escolha objetiva completamente errada.
    displayed_as_input = payload.get("response_format") == "input"
    is_objective = not displayed_as_input and (exercise_type in ("choice", "reading", "dialogue") or (
        exercise_type == "listening" and exercise.get("response_type") != "input"
    ))
    if is_objective:
        correct = any(normalize_answer(answer_text) == normalize_answer(item) for item in valid)
        score = 1.0 if correct else 0.0
        verdict = "correct" if correct else "wrong"
        proximity_note = "Resposta exata." if correct else "A alternativa escolhida muda a construção ou o sentido."
    else:
        comparisons = [(*partial_score(answer_text, item), item) for item in valid]
        score, verdict, proximity_note, closest = max(comparisons, key=lambda item: item[0]) if comparisons else (0.0, "wrong", "Sem gabarito.", canonical)
        canonical = closest or canonical
        correct = score >= 1
    return {
        "is_correct": correct,
        "is_partial": 0 < score < 1,
        "score": score,
        "verdict": verdict,
        "correct_answer": canonical,
        "message": "Correto." if correct else "Quase." if score > 0 else "Ainda não.",
        "proximity_note": proximity_note,
        "explanation": exercise.get("explanation", ""),
        "feedback": exercise.get("feedback", ""),
        "transcript": exercise.get("audio_text", "") if exercise_type == "listening" else "",
        "after_audio": exercise.get("after_audio"),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LinguaLab/1.0"

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
        self.send_response(HTTPStatus.OK)
        offline = path.suffix == ".wav"
        self.send_header("Content-Type", "audio/wav" if offline else "audio/mpeg")
        self.send_header("Content-Length", str(len(raw)))
        # A voz offline é provisória: o navegador não deve guardá-la para sempre.
        self.send_header("Cache-Control", "no-store" if offline else "public, max-age=31536000, immutable")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # O navegador cancelou o áudio (troca de fala, "Parar", próxima tela).
            pass

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("Corpo da requisição grande demais")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/answer":
            ex_id = str(payload.get("exercise_id", ""))
            exercise = self.app.exercise(ex_id)
            if not exercise:
                self.send_json({"error": "Exercício não encontrado"}, HTTPStatus.NOT_FOUND)
                return
            try:
                result = grade(exercise, payload)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            attempt_id = self.app.db.save_attempt(payload, exercise, result)
            result["attempt_id"] = attempt_id
            result["summary"] = self.app.db.summary(str(payload.get("course_id") or ""))
            self.send_json(result)
            return

        if parsed.path == "/api/classify":
            ok = self.app.db.classify_attempt(
                int(payload.get("attempt_id", 0)), str(payload.get("category", ""))
            )
            self.send_json({"ok": ok}, 200 if ok else 400)
            return

        if parsed.path == "/api/report":
            ex_id = str(payload.get("exercise_id", ""))
            exercise = self.app.exercise(ex_id)
            if not exercise:
                self.send_json({"error": "Exercício não encontrado"}, HTTPStatus.NOT_FOUND)
                return
            report_id = self.app.db.save_content_report(payload, exercise)
            self.send_json({"ok": True, "report_id": report_id})
            return

        if parsed.path == "/api/reload-content":
            try:
                self.app.content.load()
                self.send_json({"ok": True, "count": len(self.app.content.exercises)})
            except Exception as exc:  # conteúdo local: devolver erro legível
                self.send_json({"error": str(exc)}, 400)
            return

        if parsed.path == "/api/session/save":
            try:
                saved = self.app.db.sessions.save(payload)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"ok": True, **saved})
            return

        if parsed.path in ("/api/session/complete", "/api/session/discard"):
            status = "completed" if parsed.path.endswith("complete") else "discarded"
            ok = self.app.db.sessions.finish(str(payload.get("key") or ""), status)
            if ok:
                self.app.db.write_live_exports()
            self.send_json({"ok": ok})
            return

        if parsed.path == "/api/update/apply":
            # Impede que outra página aberta no navegador dispare a atualização.
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.send_json({"error": "Origem não permitida."}, HTTPStatus.FORBIDDEN)
                return
            try:
                self.app.updater.start_apply()
            except UpdateError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"ok": True})
            return

        if parsed.path == "/api/export":
            self.app.db.write_live_exports()
            self.send_json({
                "ok": True,
                "files": ["analise_atual.json", "respostas.csv", "relatorio_atual.md", "problemas_reportados.md"],
            })
            return

        self.send_json({"error": "Endpoint não encontrado"}, HTTPStatus.NOT_FOUND)

    def handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/update/check":
            self.send_json(self.app.updater.check(force=query.get("force", ["0"])[0] == "1"))
            return

        if path == "/api/update/status":
            self.send_json(self.app.updater.status())
            return

        if path == "/api/bootstrap":
            course_id = query.get("course_id", ["russian"])[0]
            if course_id not in {course["id"] for course in COURSES}:
                course_id = "russian"
            self.send_json({
                "app_version": APP_VERSION,
                "session_id": secrets.token_urlsafe(10),
                "courses": COURSES,
                "features": {
                    "tts": edge_tts is not None,
                    "dictionary": DICTIONARY_PATH.exists(),
                    "lexical_minimum": LEXICAL_MINIMUM_PATH.exists(),
                    "self_update": FROZEN,
                },
                "units": [self.app.content.public_unit(unit) for unit in self.app.content.units],
                "summary": self.app.db.summary(course_id),
            })
            return

        if path == "/api/exercises":
            unit_id = query.get("unit_id", [""])[0]
            course_id = query.get("course_id", ["russian"])[0]
            mode = query.get("mode", ["study"])[0]
            if unit_id:
                lock_state = {row["unit_id"]: row["unlocked"] for row in self.app.db.unit_progress(course_id)}
                if unit_id in lock_state and not lock_state[unit_id]:
                    self.send_json({"error": "Unidade bloqueada: conclua a unidade anterior primeiro."}, HTTPStatus.FORBIDDEN)
                    return
            items = list(self.app.content.exercises.values())
            items = [item for item in items if self.app.content.exercise_unit[item["id"]].get("course_id", "russian") == course_id]
            if unit_id:
                items = [item for item in items if item["unit_id"] == unit_id]
            if mode == "diagnostic":
                items = [item for item in items if item.get("diagnostic")]
            elif mode == "review":
                due = set(self.app.db.due_ids())
                items = [item for item in items if item["id"] in due]
                if course_id == "russian":
                    items.extend(filter(None, (self.app.lexical.exercise(item_id) for item_id in due if item_id.startswith(("lm-", "lv-")))))
            elif mode == "difficult":
                difficult = set(self.app.db.difficult_ids())
                items = [item for item in items if item["id"] in difficult]
                if course_id == "russian":
                    items.extend(filter(None, (self.app.lexical.exercise(item_id) for item_id in difficult if item_id.startswith(("lm-", "lv-")))))
            elif mode == "flashcards":
                items = [item for item in items if item.get("type") == "flashcard"]
            elif mode == "writing":
                items = [item for item in items if item.get("type") == "open_text"]
            elif mode == "study":
                items = [item for item in items if item.get("type") != "open_text"]
            # O módulo "Prefixos" tem página própria: nunca vaza para uma
            # sessão genérica de "Estudar" sem unidade escolhida.
            if not unit_id and mode not in {"review", "difficult"}:
                items = [
                    item for item in items
                    if item["unit_id"] != PREFIX_VERBS_UNIT_ID
                    and not (item["unit_id"].startswith(VOCAB_UNIT_PREFIX) and mode != "writing")
                ]
            # Cartões de apresentação não têm correção: nunca entram em revisão.
            items = [item for item in items if item.get("type") not in UNGRADED_TYPES]
            self.send_json({
                "exercises": session_exercises(items, self.app.content.public_exercise),
            })
            return

        if path == "/api/session/active":
            course_id = query.get("course_id", [""])[0]
            self.send_json({"sessions": self.app.db.sessions.active(course_id)})
            return

        if path == "/api/session/get":
            row = self.app.db.sessions.row(query.get("key", [""])[0])
            if not row:
                self.send_json({"error": "Sessão não encontrada ou já concluída."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(self.app.rebuild_session(row))
            return

        if path == "/api/progress/map":
            data = self.app.progress_map(query.get("scope", [""])[0])
            if data is None:
                self.send_json({"error": "Escopo desconhecido."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(data)
            return

        if path == "/api/vocab/bootstrap":
            store = self.app.content.vocab
            self.send_json({
                "lessons": [store.public_lesson(lesson) for lesson in store.lessons],
                "progress": self.app.db.vocab_progress(),
                "coverage": self.app.db.lexical_coverage(),
            })
            return

        if path == "/api/vocab/lesson":
            store = self.app.content.vocab
            lesson = store.lessons_by_id.get(query.get("id", [""])[0])
            if not lesson:
                self.send_json({"error": "Lição não encontrada."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({
                "lesson": store.public_lesson(lesson, with_dialogue=True),
                "progress": self.app.db.vocab_progress().get(lesson["id"], {}),
            })
            return

        if path == "/api/vocab/session":
            store = self.app.content.vocab
            lesson_id = query.get("id", [""])[0]
            part = query.get("part", ["all"])[0]
            if lesson_id not in store.lessons_by_id:
                self.send_json({"error": "Lição não encontrada."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({
                "exercises": session_exercises(store.session(lesson_id, part), self.app.content.public_exercise),
            })
            return

        if path == "/api/prefixes/bootstrap":
            module = self.app.content.prefix_module
            counts = module.get("stage_counts", {})
            self.send_json({
                "title": module.get("title", "Verbos com prefixo"),
                "description": module.get("description", ""),
                "intro": module.get("intro", []),
                "stages": [
                    {**stage, "count": counts.get(stage["id"], 0)}
                    for stage in module.get("stages", [])
                ],
                "total": len(module.get("exercises", [])),
                "progress": self.app.db.prefix_progress(),
            })
            return

        if path == "/api/prefixes/questions":
            module = self.app.content.prefix_module
            stage = query.get("stage", ["all"])[0]
            try:
                limit = int(query.get("limit", ["16"])[0])
            except ValueError:
                limit = 16
            limit = max(1, min(limit, 60))
            pool = [
                dict(item) for item in module.get("exercises", [])
                if stage in ("all", "") or item.get("stage") == stage
            ]
            random.shuffle(pool)
            pool = pool[:limit]
            self.send_json({
                "exercises": session_exercises(pool, self.app.content.public_exercise),
            })
            return

        if path == "/api/morphology/bootstrap":
            self.send_json({
                "inventory": self.app.lexical.metadata(),
                "coverage": self.app.db.lexical_coverage(),
            })
            return

        if path == "/api/morphology/questions":
            kind = query.get("kind", ["morphology"])[0]
            if kind not in {"morphology", "vocabulary"}:
                kind = "morphology"
            pos = query.get("pos", [""])[0]
            if pos not in {"", "noun", "adjective", "verb", "adverb", "other"}:
                pos = ""
            case_code = query.get("case", [""])[0]
            if case_code not in {"", "gen", "dat", "acc", "inst", "prep"}:
                case_code = ""
            number_code = query.get("number", [""])[0]
            if number_code not in {"", "sg", "pl"}:
                number_code = ""
            try:
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                limit = 20
            unseen = query.get("unseen", ["0"])[0] == "1"
            response_type = query.get("response", ["choice"])[0]
            if response_type not in {"choice", "input"}:
                response_type = "choice"
            excluded = self.app.db.lexeme_seen() if unseen else set()
            exercises = self.app.lexical.questions(
                kind, limit, pos, case_code, number_code, excluded
            )
            if kind == "morphology" and response_type == "input":
                # O gabarito continua apenas no servidor. O POST /api/answer
                # corrige pelo exercício original, identificado pelo mesmo ID.
                exercises = [
                    {
                        **exercise,
                        "type": "input",
                        "instruction": "Produza a forma completa sem olhar alternativas.",
                        "options": [],
                    }
                    for exercise in exercises
                ]
            self.send_json({
                "exercises": session_exercises(exercises, self.app.lexical.public_exercise),
                "coverage": self.app.db.lexical_coverage(),
            })
            return

        if path == "/api/reveal":
            ex_id = query.get("id", [""])[0]
            exercise = self.app.exercise(ex_id)
            if not exercise:
                self.send_json({"error": "Exercício não encontrado"}, 404)
                return
            self.send_json(self.app.content.reveal(exercise))
            return

        if path == "/api/summary":
            course_id = query.get("course_id", [""])[0]
            self.send_json(self.app.db.summary(course_id))
            return

        if path == "/api/pending-writing":
            course_id = query.get("course_id", [""])[0]
            self.send_json({"items": self.app.db.pending_writing(course_id)})
            return

        if path == "/api/reports":
            course_id = query.get("course_id", [""])[0]
            self.send_json({"items": self.app.db.content_reports(course_id=course_id)})
            return

        if path == "/api/dictionary":
            word = query.get("word", [""])[0]
            self.send_json(self.app.dictionary.lookup(word))
            return

        if path == "/api/tts":
            text_value = query.get("text", [""])[0]
            course_id = query.get("course_id", ["russian"])[0]
            mode = query.get("mode", ["target"])[0]
            speaker = query.get("voice", [""])[0]
            try:
                audio_path = self.app.tts.audio_for(text_value, course_id, mode=mode, speaker=speaker)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self.send_json({"error": f"Não foi possível gerar o áudio: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_audio(audio_path)
            return

        if path == "/api/lesson-audio":
            unit_id = query.get("unit_id", [""])[0]
            block_raw = query.get("block", ["all"])[0]
            unit = self.app.content.units_by_id.get(unit_id)
            if not unit:
                self.send_json({"error": "Unidade não encontrada."}, HTTPStatus.NOT_FOUND)
                return
            try:
                block_index = None if block_raw in ("", "all") else int(block_raw)
            except ValueError:
                self.send_json({"error": "Índice de bloco inválido."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                script = lesson_script(unit, block_index)
                audio_path = self.app.tts.audio_for(script, unit.get("course_id", "russian"), mode="lesson")
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self.send_json({"error": f"Não foi possível gerar o áudio: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_audio(audio_path)
            return

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
        suffix_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }
        raw = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", suffix_types.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class AppServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]):
        self.content = ContentStore(UNITS_DIR)
        self.lexical = LexicalMinimumStore(LEXICAL_MINIMUM_PATH)
        self.db = Database(DB_PATH, self.content, self.lexical)
        self.dictionary = DictionaryStore(DICTIONARY_PATH, COURSE_LEXICON_PATH)
        self.tts = TTSService(TTS_CACHE_DIR)
        self.updater = Updater(APP_VERSION, USER_DIR, on_restart=lambda: threading.Thread(target=self.shutdown).start())
        self.db.reconcile_unit_completion()
        self.db.write_live_exports()
        super().__init__(address, handler)

    def exercise(self, exercise_id: str) -> dict | None:
        return self.content.exercises.get(exercise_id) or self.lexical.exercise(exercise_id)

    def public_exercise(self, exercise: dict) -> dict:
        if str(exercise.get("id", "")).startswith(("lm-", "lv-")):
            return self.lexical.public_exercise(exercise)
        return self.content.public_exercise(exercise)

    def rebuild_session(self, row: dict) -> dict:
        """Reconstrói a fila de uma sessão salva, sem gabarito.

        As alternativas voltam na mesma ordem em que o aluno as viu. Exercícios
        que não existem mais (conteúdo editado desde então) são descartados e
        o ponto de retomada é recalculado.
        """
        payload = row["payload"]
        resume = int(row["resume_index"])
        exercises: list[dict] = []
        statuses: list[str] = []
        dropped_before = dropped = 0
        for index, entry in enumerate(payload["queue"]):
            base = self.exercise(entry["id"])
            if not base:
                dropped += 1
                if index < resume:
                    dropped_before += 1
                continue
            public = dict(self.public_exercise(base))
            options = entry.get("options")
            if options and set(options) == set(public.get("options") or []):
                public["options"] = list(options)
            if entry.get("fmt") == "input":
                public.update(type="input", options=[], instruction="Produza a forma completa sem olhar alternativas.")
            if entry.get("retry"):
                public["retry"] = True
                public["phase"] = "↻ RECUPERAR DE NOVO"
            exercises.append(public)
            statuses.append(payload["status"][index] if index < len(payload["status"]) else "new")
        resume = max(0, min(len(exercises), resume - dropped_before))
        session = {key: row[key] for key in (
            "key", "kind", "course_id", "title", "answered", "elapsed_ms", "created_at", "updated_at",
        )}
        session.update(resume_index=resume, total=len(exercises))
        return {
            "session": session,
            "exercises": exercises,
            "status": statuses,
            "results": payload["results"],
            "meta": payload["meta"],
            "dropped": dropped,
        }

    def progress_map(self, scope: str) -> dict | None:
        """Mapa pergunta a pergunta de uma unidade ou lição de vocabulário.

        Cada célula traz o último resultado, o número de tentativas e se o
        item já está dominado (mesma regra cumulativa da trilha).
        """
        kind, _, ident = scope.partition(":")
        entries: list[tuple[dict, str]] = []
        title = ""
        if kind == "vocab":
            store = self.content.vocab
            lesson = store.lessons_by_id.get(ident)
            if not lesson:
                return None
            title = lesson["title"]
            order = {exercise["id"]: position for position, exercise in enumerate(lesson["generated"])}
            parts = store.lesson_parts(lesson)
            parts["2"] = sorted(parts["2"], key=lambda exercise: order[exercise["id"]])
            for part in ("1", "2", "3"):
                entries.extend((exercise, part) for exercise in parts[part] if exercise["type"] not in UNGRADED_TYPES)
        elif kind == "unit":
            unit = self.content.units_by_id.get(ident)
            if not unit:
                return None
            title = unit["title"]
            entries = [(exercise, "") for exercise in unit_session_order(unit)]
        else:
            return None
        ids = [exercise["id"] for exercise, _ in entries]
        summary = self.db.sessions.attempt_summary(ids)
        cleared = self.db.cleared_exercise_ids()
        cells = []
        counts = {"new": 0, "correct": 0, "partial": 0, "wrong": 0, "pending": 0}
        for position, (exercise, part) in enumerate(entries, start=1):
            info = summary.get(exercise["id"])
            if not info:
                state = "new"
            elif info["pending"]:
                state = "pending"
            elif (info["last_score"] or 0) >= 1:
                state = "correct"
            elif (info["last_score"] or 0) > 0:
                state = "partial"
            else:
                state = "wrong"
            counts[state] += 1
            cells.append({
                "id": exercise["id"],
                "n": position,
                "part": part,
                "type": exercise.get("type"),
                "label": str(exercise.get("prompt") or exercise.get("front") or exercise.get("head") or "")[:110],
                "state": state,
                "mastered": exercise["id"] in cleared,
                "attempts": info["attempts"] if info else 0,
                "last_at": info["last_at"] if info else None,
            })
        return {"scope": scope, "title": title, "cells": cells, "counts": counts, "total": len(cells)}


def already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/update/status", timeout=1.5) as response:
            return "phase" in json.load(response)
    except Exception:  # noqa: BLE001 - qualquer falha significa "não há servidor nosso nessa porta"
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="LinguaLab local")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    url = f"http://{args.host}:{args.port}"
    if already_running(url):
        # Segundo clique no atalho: só traz a página de volta ao navegador.
        print(f"LinguaLab já está aberto em {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    server = AppServer((args.host, args.port), AppHandler)
    print(f"LinguaLab disponível em {url}")
    print("Feche esta janela (ou pressione Ctrl+C) para encerrar." if FROZEN else "Pressione Ctrl+C para encerrar.")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
