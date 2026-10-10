#!/usr/bin/env python3
"""Baixa os CSVs oficiais do OpenRussian e cria um índice morfológico local.

Fonte: https://github.com/Badestrand/russian-dictionary
Licença dos dados: CC BY-SA 4.0.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import sys
import unicodedata
import urllib.request
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
OUTPUT = BASE / "data" / "openrussian.sqlite3"
TEMP = OUTPUT.with_suffix(".sqlite3.tmp")
RAW_BASE = "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master"

SOURCES = {
    "noun": "nouns.csv",
    "adjective": "adjectives.csv",
    "verb": "verbs.csv",
    "other": "others.csv",
}

CASE_NAMES = {
    "nom": "именительный падеж",
    "gen": "родительный падеж",
    "dat": "дательный падеж",
    "acc": "винительный падеж",
    "inst": "творительный падеж",
    "prep": "предложный падеж",
}


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "").lower()
    text = text.replace("ё", "е").replace("'", "").replace("´", "").replace("*", "")
    text = re.sub(r"[^а-я-]", "", text)
    return text


def variants(value: str) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for part in re.split(r"[,;/]", value):
        form = normalize(part)
        if form and form not in result:
            result.append(form)
    return result


def noun_forms(row: dict[str, str]) -> list[tuple[str, str]]:
    forms: list[tuple[str, str]] = []
    for number_key, number_label in (("sg", "ед. ч."), ("pl", "мн. ч.")):
        for case_key, case_label in CASE_NAMES.items():
            for form in variants(row.get(f"{number_key}_{case_key}", "")):
                forms.append((form, f"{case_label}, {number_label}"))
    return forms


def adjective_forms(row: dict[str, str]) -> list[tuple[str, str]]:
    forms: list[tuple[str, str]] = []
    genders = (("m", "м. р."), ("f", "ж. р."), ("n", "ср. р."), ("pl", "мн. ч."))
    for gender_key, gender_label in genders:
        for case_key, case_label in CASE_NAMES.items():
            for form in variants(row.get(f"decl_{gender_key}_{case_key}", "")):
                forms.append((form, f"{case_label}, {gender_label}"))
    for key, label in (
        ("comparative", "сравнительная степень"),
        ("superlative", "превосходная степень"),
        ("short_m", "краткая форма, м. р."),
        ("short_f", "краткая форма, ж. р."),
        ("short_n", "краткая форма, ср. р."),
        ("short_pl", "краткая форма, мн. ч."),
    ):
        for form in variants(row.get(key, "")):
            forms.append((form, label))
    return forms


def verb_forms(row: dict[str, str]) -> list[tuple[str, str]]:
    labels = {
        "imperative_sg": "повелительное наклонение, ед. ч.",
        "imperative_pl": "повелительное наклонение, мн. ч.",
        "past_m": "прошедшее время, м. р.",
        "past_f": "прошедшее время, ж. р.",
        "past_n": "прошедшее время, ср. р.",
        "past_pl": "прошедшее время, мн. ч.",
        "presfut_sg1": "настоящее/будущее время, 1 л. ед. ч.",
        "presfut_sg2": "настоящее/будущее время, 2 л. ед. ч.",
        "presfut_sg3": "настоящее/будущее время, 3 л. ед. ч.",
        "presfut_pl1": "настоящее/будущее время, 1 л. мн. ч.",
        "presfut_pl2": "настоящее/будущее время, 2 л. мн. ч.",
        "presfut_pl3": "настоящее/будущее время, 3 л. мн. ч.",
    }
    forms: list[tuple[str, str]] = []
    for key, label in labels.items():
        for form in variants(row.get(key, "")):
            forms.append((form, label))
    return forms


def iter_csv(filename: str):
    url = f"{RAW_BASE}/{filename}"
    print(f"Baixando {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "RusskiTrainer/1.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        wrapper = io.TextIOWrapper(response, encoding="utf-8", errors="replace", newline="")
        yield from csv.DictReader(wrapper, delimiter="\t", quoting=csv.QUOTE_MINIMAL)


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if TEMP.exists():
        TEMP.unlink()
    conn = sqlite3.connect(TEMP)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode = OFF;
            PRAGMA synchronous = OFF;
            PRAGMA temp_store = MEMORY;
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                lemma TEXT NOT NULL,
                accented TEXT,
                pos TEXT NOT NULL,
                translations_en TEXT,
                gender TEXT,
                aspect TEXT,
                partner TEXT,
                attributes_json TEXT NOT NULL
            );
            CREATE TABLE form_index (
                form TEXT NOT NULL,
                entry_id INTEGER NOT NULL,
                grammar TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id)
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        total_entries = 0
        total_forms = 0
        for pos, filename in SOURCES.items():
            for row in iter_csv(filename):
                lemma = normalize(row.get("bare", ""))
                if not lemma:
                    continue
                attributes = {
                    key: value for key, value in row.items()
                    if value and key not in {"bare", "accented", "translations_en", "translations_de"}
                }
                cursor = conn.execute(
                    """
                    INSERT INTO entries
                        (lemma, accented, pos, translations_en, gender, aspect, partner, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lemma,
                        row.get("accented", ""),
                        pos,
                        row.get("translations_en", ""),
                        row.get("gender", ""),
                        row.get("aspect", ""),
                        normalize(row.get("partner", "")),
                        json.dumps(attributes, ensure_ascii=False),
                    ),
                )
                entry_id = int(cursor.lastrowid)
                indexed = {(lemma, "словарная форма")}
                if pos == "noun":
                    indexed.update(noun_forms(row))
                elif pos == "adjective":
                    indexed.update(adjective_forms(row))
                elif pos == "verb":
                    indexed.update(verb_forms(row))
                    indexed.add((lemma, "инфинитив"))
                conn.executemany(
                    "INSERT INTO form_index (form, entry_id, grammar) VALUES (?, ?, ?)",
                    ((form, entry_id, grammar) for form, grammar in indexed if form),
                )
                total_entries += 1
                total_forms += len(indexed)
                if total_entries % 5000 == 0:
                    conn.commit()
                    print(f"  {total_entries} verbetes…", flush=True)

        conn.executescript(
            """
            CREATE INDEX idx_form_index_form ON form_index(form);
            CREATE INDEX idx_entries_lemma ON entries(lemma);
            ANALYZE;
            """
        )
        metadata = {
            "source": "OpenRussian / Badestrand russian-dictionary",
            "source_url": "https://github.com/Badestrand/russian-dictionary",
            "license": "CC BY-SA 4.0",
            "entries": str(total_entries),
            "forms": str(total_forms),
        }
        conn.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
        conn.commit()
    finally:
        conn.close()
    os.replace(TEMP, OUTPUT)
    print(f"Dicionário criado: {OUTPUT} ({total_entries} verbetes, {total_forms} formas).")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        if TEMP.exists():
            TEMP.unlink()
        print(f"Falha ao importar OpenRussian: {exc}", file=sys.stderr)
        raise
