#!/usr/bin/env python3
"""Extrai o inventário do Лексический минимум ТРКИ-II e gera jogos morfológicos.

O PDF pertence ao usuário e permanece fora do aplicativo. O banco derivado guarda
somente cabeçalhos lexicais, referências de página e formas necessárias aos jogos.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
WORKSPACE = BASE.parent
PDF = WORKSPACE / "Leksicheskii_minimum_po_russkomu_iazyku_kak_inostrannomu_2_uroven.pdf"
OPENRUSSIAN = BASE / "data" / "openrussian.sqlite3"
OUTPUT = BASE / "data" / "lexical_minimum.sqlite3"
TEMP = OUTPUT.with_suffix(".sqlite3.tmp")

CASES = {
    "nom": "именительный падеж",
    "gen": "родительный падеж",
    "dat": "дательный падеж",
    "acc": "винительный падеж",
    "inst": "творительный падеж",
    "prep": "предложный падеж",
}
NUMBERS = {"sg": "ед. ч.", "pl": "мн. ч."}
GENDERS = {"m": "м. р.", "f": "ж. р.", "n": "ср. р.", "pl": "мн. ч."}
MANUAL_TRANSLATIONS = {"сапоги": "high boots"}


def lookup_form(value: str) -> str:
    return value.lower().replace("ё", "е").replace("k", "")


def clean_stress(value: str) -> str:
    text = re.sub(r"(?<=[А-Яа-яЁё])k|k(?=[А-Яа-яЁё])", "", value)
    text = text.replace("'", "").replace("´", "").replace("*", "")
    text = re.sub(r"(?<=[А-Яа-яЁё])[A-Za-z](?=[А-Яа-яЁё])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def first_variant(value: str) -> str:
    if not value:
        return ""
    return clean_stress(re.split(r"[,;/]", value)[0])


def common_segmentation(base: str, target: str) -> tuple[str, str]:
    index = 0
    for left, right in zip(base.lower(), target.lower()):
        if left != right:
            break
        index += 1
    if index < 2:
        return base, target
    return target[:index], target[index:] or "∅"


def extract_items() -> list[dict]:
    if not PDF.exists():
        raise FileNotFoundError(f"PDF não encontrado: {PDF}")
    result = subprocess.run(
        ["pdftotext", "-f", "11", "-l", "136", "-layout", str(PDF), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    items: list[dict] = []
    page = 10
    seen_rows: set[tuple[int, str]] = set()
    for page_text in result.stdout.split("\f"):
        page += 1
        for line in page_text.splitlines():
            if not line or line[0].isspace():
                continue
            layout_line = re.sub(r"(?<=[А-Яа-яЁё])k|k(?=[А-Яа-яЁё])", "", line)
            layout_line = layout_line.replace("'", "").replace("´", "").replace("*", "")
            layout_line = re.sub(r"(?<=[А-Яа-яЁё])[A-Za-z](?=[А-Яа-яЁё])", "", layout_line)
            match = re.match(r"^([А-Яа-яЁё][А-Яа-яЁё-]*)", layout_line)
            if not match:
                continue
            lemma = match.group(1)
            if len(lemma) == 1 and lemma.isupper():
                continue
            split = re.match(r"^(.*?\S)\s{3,}(\(?[A-Za-z].*)$", layout_line)
            raw_entry = clean_stress(split.group(1)) if split else clean_stress(layout_line[:72])
            translation = split.group(2).strip() if split else ""
            key = (page, raw_entry)
            if key in seen_rows:
                continue
            seen_rows.add(key)
            items.append({
                "lemma": lemma,
                "lookup": lookup_form(lemma),
                "raw_entry": raw_entry,
                "translation_en": translation,
                "source_page": page,
            })
    return items


def option_pool(attributes: dict, prefix: str) -> list[str]:
    result: list[str] = []
    for key, value in attributes.items():
        if prefix in {"sg_", "pl_"} and key not in {f"{prefix}{case}" for case in CASES}:
            continue
        if prefix == "decl_" and not re.fullmatch(r"decl_(m|f|n|pl)_(nom|gen|dat|acc|inst|prep)", key):
            continue
        form = first_variant(str(value))
        if form and form not in result:
            result.append(form)
    return result


def choose_options(answer: str, candidates: list[str], seed: str) -> list[str]:
    alternatives = list(dict.fromkeys(item for item in candidates if item and item != answer))
    alternatives.sort(key=lambda item: hashlib.sha1(f"{seed}|{item}".encode()).hexdigest())
    options = [answer, *alternatives[:3]]
    options.sort(key=lambda item: hashlib.sha1(f"option|{seed}|{item}".encode()).hexdigest())
    return options


def paradigm_matches(lemma: str, pos: str, attributes: dict) -> bool:
    """Descarta os poucos paradigmas corrompidos presentes na base aberta."""
    keys = ("sg_nom", "pl_nom") if pos == "noun" else (
        "decl_m_nom", "decl_f_nom", "decl_n_nom", "decl_pl_nom"
    )
    nominatives = {lookup_form(first_variant(attributes.get(key, ""))) for key in keys}
    return lemma in nominatives


def build() -> None:
    items = extract_items()
    if TEMP.exists():
        TEMP.unlink()
    output = sqlite3.connect(TEMP)
    source = sqlite3.connect(OPENRUSSIAN)
    source.row_factory = sqlite3.Row
    try:
        output.executescript(
            """
            PRAGMA journal_mode = OFF;
            PRAGMA synchronous = OFF;
            CREATE TABLE lexical_items (
                id INTEGER PRIMARY KEY,
                lemma TEXT NOT NULL,
                lookup TEXT NOT NULL,
                raw_entry TEXT NOT NULL,
                translation_en TEXT,
                source_page INTEGER NOT NULL,
                matched INTEGER NOT NULL DEFAULT 0,
                parts_of_speech TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE morphology_cards (
                id TEXT PRIMARY KEY,
                lemma TEXT NOT NULL,
                display_lemma TEXT NOT NULL,
                pos TEXT NOT NULL,
                gender TEXT,
                case_code TEXT NOT NULL,
                case_ru TEXT NOT NULL,
                number_code TEXT NOT NULL,
                number_ru TEXT NOT NULL,
                target_gender TEXT,
                answer TEXT NOT NULL,
                stem TEXT NOT NULL,
                ending TEXT NOT NULL,
                options_json TEXT NOT NULL,
                translation_en TEXT,
                source_page INTEGER NOT NULL
            );
            CREATE TABLE vocabulary_cards (
                id TEXT PRIMARY KEY,
                lemma TEXT NOT NULL,
                display_lemma TEXT NOT NULL,
                translation_en TEXT NOT NULL,
                parts_of_speech TEXT NOT NULL DEFAULT '',
                options_json TEXT NOT NULL,
                source_page INTEGER NOT NULL
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        card_keys: set[tuple] = set()
        matched_items = 0
        morphology_lemmas: set[str] = set()
        for item in items:
            matches = source.execute(
                "SELECT * FROM entries WHERE lemma = ? ORDER BY id", (item["lookup"],)
            ).fetchall()
            parts = sorted({row["pos"] for row in matches})
            translation = item["translation_en"] or (
                matches[0]["translations_en"] if matches else ""
            ) or MANUAL_TRANSLATIONS.get(item["lookup"], "")
            cursor = output.execute(
                """
                INSERT INTO lexical_items
                    (lemma, lookup, raw_entry, translation_en, source_page, matched, parts_of_speech)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["lemma"], item["lookup"], item["raw_entry"], translation,
                    item["source_page"], int(bool(matches)), ",".join(parts),
                ),
            )
            item_id = int(cursor.lastrowid)
            if matches:
                matched_items += 1
            for match in matches:
                if match["pos"] not in {"noun", "adjective"}:
                    continue
                attributes = json.loads(match["attributes_json"] or "{}")
                if not paradigm_matches(item["lookup"], match["pos"], attributes):
                    continue
                display_lemma = item["lemma"]
                if match["pos"] == "noun":
                    candidates = option_pool(attributes, "sg_") + option_pool(attributes, "pl_")
                    for number_code, number_ru in NUMBERS.items():
                        for case_code, case_ru in CASES.items():
                            if case_code == "nom":
                                continue
                            answer = first_variant(attributes.get(f"{number_code}_{case_code}", ""))
                            if not answer:
                                continue
                            options = choose_options(answer, candidates, f"{item_id}|{match['id']}|{number_code}|{case_code}")
                            if len(set(options)) < 3:
                                continue
                            key = (item["lookup"], "noun", number_code, case_code, answer)
                            if key in card_keys:
                                continue
                            card_keys.add(key)
                            stem, ending = common_segmentation(display_lemma, answer)
                            card_id = f"lm-{item_id}-{match['id']}-n-{number_code}-{case_code}"
                            output.execute(
                                "INSERT INTO morphology_cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    card_id, item["lookup"], display_lemma, "noun", match["gender"] or "",
                                    case_code, case_ru, number_code, number_ru, "", answer, stem, ending,
                                    json.dumps(options, ensure_ascii=False),
                                    translation or match["translations_en"], item["source_page"],
                                ),
                            )
                            morphology_lemmas.add(item["lookup"])
                else:
                    candidates = option_pool(attributes, "decl_")
                    for gender_code, gender_ru in GENDERS.items():
                        number_code = "pl" if gender_code == "pl" else "sg"
                        number_ru = NUMBERS[number_code]
                        for case_code, case_ru in CASES.items():
                            if case_code == "nom":
                                continue
                            answer = first_variant(attributes.get(f"decl_{gender_code}_{case_code}", ""))
                            if not answer:
                                continue
                            options = choose_options(answer, candidates, f"{item_id}|{match['id']}|{gender_code}|{case_code}")
                            if len(set(options)) < 3:
                                continue
                            key = (item["lookup"], "adjective", gender_code, case_code, answer)
                            if key in card_keys:
                                continue
                            card_keys.add(key)
                            stem, ending = common_segmentation(display_lemma, answer)
                            card_id = f"lm-{item_id}-{match['id']}-a-{gender_code}-{case_code}"
                            output.execute(
                                "INSERT INTO morphology_cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    card_id, item["lookup"], display_lemma, "adjective", "",
                                    case_code, case_ru, number_code, number_ru,
                                    gender_ru if gender_code != "pl" else "",
                                    answer, stem, ending,
                                    json.dumps(options, ensure_ascii=False),
                                    translation or match["translations_en"], item["source_page"],
                                ),
                            )
                            morphology_lemmas.add(item["lookup"])

        vocabulary_rows = output.execute(
            """
            SELECT lookup, MIN(lemma) AS display_lemma,
                   MAX(translation_en) AS translation_en,
                   MAX(parts_of_speech) AS parts_of_speech,
                   MIN(source_page) AS source_page
            FROM lexical_items
            GROUP BY lookup
            ORDER BY lookup
            """
        ).fetchall()
        vocabulary = [dict(zip(
            ["lookup", "display_lemma", "translation_en", "parts_of_speech", "source_page"], row
        )) for row in vocabulary_rows]
        by_pos: dict[str, list[dict]] = {}
        for row in vocabulary:
            primary_pos = (row["parts_of_speech"] or "other").split(",")[0]
            by_pos.setdefault(primary_pos, []).append(row)
        for index, row in enumerate(vocabulary):
            primary_pos = (row["parts_of_speech"] or "other").split(",")[0]
            candidate_rows = by_pos.get(primary_pos, [])
            if len(candidate_rows) < 4:
                candidate_rows = vocabulary
            target_translation = (row["translation_en"] or "").casefold()
            candidates = [
                candidate["display_lemma"] for candidate in candidate_rows
                if (candidate["translation_en"] or "").casefold() != target_translation
            ]
            options = choose_options(row["display_lemma"], candidates, f"vocab|{row['lookup']}|{index}")
            output.execute(
                "INSERT INTO vocabulary_cards VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"lv-{index + 1}", row["lookup"], row["display_lemma"],
                    row["translation_en"] or MANUAL_TRANSLATIONS.get(row["lookup"], "meaning unavailable"),
                    row["parts_of_speech"], json.dumps(options, ensure_ascii=False), row["source_page"],
                ),
            )

        output.executescript(
            """
            CREATE INDEX idx_lexical_lookup ON lexical_items(lookup);
            CREATE INDEX idx_cards_filter ON morphology_cards(pos, case_code, number_code);
            CREATE INDEX idx_cards_lemma ON morphology_cards(lemma);
            CREATE INDEX idx_vocab_lemma ON vocabulary_cards(lemma);
            CREATE INDEX idx_vocab_pos ON vocabulary_cards(parts_of_speech);
            """
        )
        unique_lemmas = output.execute("SELECT COUNT(DISTINCT lookup) FROM lexical_items").fetchone()[0]
        card_count = output.execute("SELECT COUNT(*) FROM morphology_cards").fetchone()[0]
        vocabulary_count = output.execute("SELECT COUNT(*) FROM vocabulary_cards").fetchone()[0]
        metadata = {
            "source": "Лексический минимум ТРКИ-II, 5-е издание",
            "source_pdf": PDF.name,
            "parsed_entries": str(len(items)),
            "unique_lemmas": str(unique_lemmas),
            "matched_entries": str(matched_items),
            "morphology_lemmas": str(len(morphology_lemmas)),
            "morphology_cards": str(card_count),
            "vocabulary_cards": str(vocabulary_count),
        }
        output.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
        output.commit()
    finally:
        source.close()
        output.close()
    TEMP.replace(OUTPUT)
    print(
        f"Inventário criado: {len(items)} entradas, {unique_lemmas} lemas únicos, "
        f"{matched_items} correspondências, {len(morphology_lemmas)} lemas declináveis, "
        f"{card_count} jogos de flexão e {vocabulary_count} jogos de vocabulário."
    )


if __name__ == "__main__":
    build()
