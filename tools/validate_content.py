#!/usr/bin/env python3
"""Valida IDs, tipos e gabaritos do conteúdo modular."""

from __future__ import annotations

import json
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
UNITS = BASE / "data" / "units"
PREFIX_VERBS = BASE / "data" / "prefix_verbs.json"
VOCAB_LESSONS = BASE / "data" / "vocab_lessons"
sys.path.insert(0, str(BASE))
TYPES = {
    "choice", "input", "correction", "sentence_order", "flashcard", "open_text",
    "match_pairs", "reading", "listening",
}
COURSES = {"russian"}


def norm(value: object) -> str:
    return " ".join(str(value).strip().lower().replace("ё", "е").rstrip(".!?…").split())


def main() -> int:
    errors: list[str] = []
    ids: set[str] = set()
    total = 0
    diagnostic = 0

    for path in sorted(UNITS.glob("*.json")):
        try:
            unit = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: JSON inválido: {exc}")
            continue
        course_id = unit.get("course_id", "russian")
        if course_id not in COURSES:
            errors.append(f"{path.name}: course_id desconhecido: {course_id}")
        for exercise in unit.get("exercises", []):
            total += 1
            ex_id = exercise.get("id", "<sem-id>")
            if ex_id in ids:
                errors.append(f"{path.name}: ID duplicado: {ex_id}")
            ids.add(ex_id)
            ex_type = exercise.get("type")
            if ex_type not in TYPES:
                errors.append(f"{ex_id}: tipo desconhecido: {ex_type}")
            if exercise.get("diagnostic"):
                diagnostic += 1
            options = exercise.get("options", [])
            if options:
                if len(set(options)) != len(options):
                    errors.append(f"{ex_id}: alternativas repetidas")
                if any(exercise.get("prompt") == option for option in options):
                    errors.append(f"{ex_id}: enunciado repetido como alternativa")
            for field in ("prompt", "instruction", "explanation", "context", "audio_text", "answer"):
                value = exercise.get(field)
                if isinstance(value, str) and any(ord(ch) in {0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF} for ch in value):
                    errors.append(f"{ex_id}: caractere invisível em '{field}'")
            for option in options:
                if any(ord(ch) in {0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF} for ch in str(option)):
                    errors.append(f"{ex_id}: caractere invisível em uma alternativa")
            if ex_type in {"choice", "reading", "listening"} and not (
                ex_type == "listening" and exercise.get("response_type") == "input"
            ):
                valid = [exercise.get("answer"), *exercise.get("valid_answers", [])]
                if not any(answer in exercise.get("options", []) for answer in valid):
                    errors.append(f"{ex_id}: gabarito não aparece nas opções")
                if ex_type == "reading" and not exercise.get("context"):
                    errors.append(f"{ex_id}: reading sem texto (context)")
                if ex_type == "listening" and not exercise.get("audio_text"):
                    errors.append(f"{ex_id}: listening sem audio_text")
            elif ex_type == "listening" and exercise.get("response_type") == "input":
                if not exercise.get("audio_text"):
                    errors.append(f"{ex_id}: listening sem audio_text")
                if not exercise.get("answer"):
                    errors.append(f"{ex_id}: ditado sem resposta")
            elif ex_type in {"input", "correction"} and not exercise.get("answer"):
                errors.append(f"{ex_id}: resposta ausente")
            elif ex_type == "sentence_order":
                answer = norm(exercise.get("answer", ""))
                joined = norm(" ".join(exercise.get("tokens", [])))
                if sorted(answer.split()) != sorted(joined.split()):
                    errors.append(f"{ex_id}: blocos não correspondem ao gabarito")
            elif ex_type == "flashcard" and not exercise.get("back"):
                errors.append(f"{ex_id}: verso ausente")
            elif ex_type == "open_text" and not exercise.get("review_notes"):
                errors.append(f"{ex_id}: critérios de correção ausentes")
            elif ex_type == "match_pairs":
                pairs = exercise.get("pairs", [])
                if not pairs:
                    errors.append(f"{ex_id}: pairs ausente ou vazio")
                lefts = [pair.get("left") for pair in pairs]
                rights = [pair.get("right") for pair in pairs]
                if any(not pair.get("left") or not pair.get("right") for pair in pairs):
                    errors.append(f"{ex_id}: par incompleto em match_pairs")
                if len(set(lefts)) != len(lefts):
                    errors.append(f"{ex_id}: valores 'left' repetidos em match_pairs")
                if len(set(rights)) != len(rights):
                    errors.append(f"{ex_id}: valores 'right' repetidos em match_pairs")

    # O módulo autônomo de prefixos não fica em data/units, mas usa o mesmo
    # motor de exercícios e precisa das mesmas garantias de conteúdo.
    if PREFIX_VERBS.exists():
        try:
            prefix_module = json.loads(PREFIX_VERBS.read_text(encoding="utf-8"))
            stage_ids = {stage.get("id") for stage in prefix_module.get("stages", [])}
            for exercise in prefix_module.get("exercises", []):
                total += 1
                ex_id = exercise.get("id", "<sem-id>")
                if ex_id in ids:
                    errors.append(f"prefix_verbs.json: ID duplicado: {ex_id}")
                ids.add(ex_id)
                if exercise.get("stage") not in stage_ids:
                    errors.append(f"{ex_id}: stage de prefixo inexistente")
                options = exercise.get("options", [])
                if exercise.get("type") != "choice":
                    errors.append(f"{ex_id}: módulo de prefixos exige tipo choice")
                if not 3 <= len(options) <= 5:
                    errors.append(f"{ex_id}: use de 3 a 5 alternativas plausíveis")
                if len(set(options)) != len(options):
                    errors.append(f"{ex_id}: alternativas repetidas")
                if exercise.get("answer") not in options:
                    errors.append(f"{ex_id}: gabarito não aparece nas opções")
                if not exercise.get("explanation"):
                    errors.append(f"{ex_id}: falta explicação comparando os distratores")
        except Exception as exc:
            prefix_module = {}
            errors.append(f"prefix_verbs.json: JSON inválido: {exc}")
    else:
        prefix_module = {}

    # Construções (data/vocab_lessons): o app usa chunk, chunk_wrong, cloze e hear como perguntas.
    for path in sorted(VOCAB_LESSONS.glob("*.json")) if VOCAB_LESSONS.exists() else []:
        try:
            lesson = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: JSON inválido: {exc}")
            continue
        for item in lesson.get("items", []):
            key = f"{lesson.get('id')}:{item.get('key')}"
            total += 1
            if not item.get("head") or not item.get("pt"):
                errors.append(f"{key}: construção sem head ou pt")
            if item.get("chunk") and item["chunk"] in item.get("chunk_wrong", []):
                errors.append(f"{key}: chunk correto repetido entre os errados")
            cloze = item.get("cloze") or {}
            if cloze and (not cloze.get("answer") or cloze["answer"] in cloze.get("wrong", [])):
                errors.append(f"{key}: lacuna sem resposta ou com resposta entre as erradas")
            hear = item.get("hear") or {}
            if hear and (not hear.get("ru") or hear.get("pt") in hear.get("wrong", [])):
                errors.append(f"{key}: escuta incompleta")

    # Base lexical: temas declarados, verbetes estudáveis com tradução, nenhum tema vazio.
    lexicon_gz = BASE / "data" / "lexicon.sqlite3.gz"
    themes = [t["id"] for t in json.loads((BASE / "data" / "themes.json").read_text(encoding="utf-8"))["themes"]]
    stats = ""

    # Aulas temáticas: estrutura, gabaritos e um tema existente por aula.
    sys.path.insert(0, str(BASE))
    from lessons import LessonStore, validate as validate_lesson

    lesson_files = sorted((BASE / "data" / "lessons").glob("*.json"))
    lesson_items = 0
    lesson_themes = set()
    for path in lesson_files:
        try:
            lesson = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: JSON inválido ({exc})")
            continue
        for problem in validate_lesson(lesson, set(themes)):
            errors.append(f"{path.name}: {problem}")
        lesson_themes.add(lesson.get("theme"))
        lesson_items += sum(LessonStore.graded_count(step) for part in lesson.get("parts", []) for step in part.get("steps", []))
    for theme in themes:
        if theme != "geral" and theme not in lesson_themes:
            errors.append(f"aulas: tema {theme} sem aula temática")
    total += lesson_items

    if not lexicon_gz.exists():
        errors.append("data/lexicon.sqlite3.gz ausente: rode tools/build_lexicon.py")
    else:
        import gzip
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "lexicon.sqlite3"
            with gzip.open(lexicon_gz, "rb") as source:
                raw.write_bytes(source.read())
            conn = sqlite3.connect(raw)
            entries = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            studyable = conn.execute("SELECT COUNT(*) FROM entries WHERE study = 1").fetchone()[0]
            missing = conn.execute("SELECT COUNT(*) FROM entries WHERE study = 1 AND (pt IS NULL OR pt = '')").fetchone()[0]
            if missing:
                errors.append(f"lexicon: {missing} verbetes estudáveis sem tradução")
            used = {row[0] for row in conn.execute("SELECT DISTINCT theme_id FROM entry_themes")}
            for theme in sorted(used - set(themes)):
                errors.append(f"lexicon: tema {theme} não existe em themes.json")
            for theme in themes:
                if theme not in used:
                    errors.append(f"lexicon: tema {theme} sem nenhuma palavra")
            unthemed = conn.execute("SELECT COUNT(*) FROM entries e WHERE NOT EXISTS (SELECT 1 FROM entry_themes t WHERE t.entry_id = e.id)").fetchone()[0]
            if unthemed:
                errors.append(f"lexicon: {unthemed} verbetes sem tema")
            content_ids = {row[0] for row in conn.execute("SELECT item_id FROM content_themes")}
            missing_content = sorted(i for i in ids if i not in content_ids)
            if missing_content:
                errors.append(f"lexicon: {len(missing_content)} exercícios sem tema (reconstrua a base): {', '.join(missing_content[:5])}")
            conn.close()
            stats = f", {entries} verbetes ({studyable} estudáveis), {len(themes)} temas"

    if errors:
        print("Erros encontrados:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {total} itens de conteúdo{stats}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
