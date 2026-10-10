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
COURSES = {"russian", "romanian", "kazakh"}


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

    # Lições «Лексика в диалоге»: o gerador já recusa falas/lacunas
    # inconsistentes; aqui conferimos o que ele produz e procuramos
    # alternativas que entreguem a resposta.
    warnings: list[str] = []
    vocab_files = sorted(VOCAB_LESSONS.glob("*.json")) if VOCAB_LESSONS.exists() else []
    vocab_count = 0
    try:
        from vocab_lessons import UNGRADED_TYPES, VocabLessonStore, gapped_answer_warnings
        store = VocabLessonStore(VOCAB_LESSONS)
        store.load()
    except Exception as exc:
        store = None
        errors.append(f"vocab_lessons: {exc}")
    if store:
        unit_ids = set()
        for path in sorted(UNITS.glob("*.json")):
            try:
                unit_ids.add(json.loads(path.read_text(encoding="utf-8"))["id"])
            except Exception:
                pass
        for lesson in store.lessons:
            if lesson["unit_id"] not in unit_ids:
                errors.append(f"{lesson['id']}: unit_id inexistente {lesson['unit_id']}")
            if len(lesson["items"]) != 8:
                warnings.append(f"{lesson['id']}: {len(lesson['items'])} construções (o modelo prevê 8)")
            for line in lesson["dialogue"]["lines"]:
                if not line.get("pt"):
                    errors.append(f"{lesson['id']}: fala sem tradução: {line['ru'][:40]}")
            for item in lesson["items"]:
                for field, size in (("chunk_wrong", 3),):
                    if len(item.get(field, [])) != size:
                        errors.append(f"{lesson['id']}/{item['key']}: {field} precisa de {size} distratores")
                for field in ("trap", "form_note", "pt", "chunk_pt"):
                    if " или " in item.get(field, ""):
                        errors.append(f"{lesson['id']}/{item['key']}: «или» num texto em português ({field})")
                if len(item["cloze"].get("wrong", [])) != 3 or len(item["hear"].get("wrong", [])) != 3:
                    errors.append(f"{lesson['id']}/{item['key']}: lacuna e escuta precisam de 3 distratores")
            for exercise in lesson["generated"]:
                vocab_count += 1
                ex_id = exercise["id"]
                if ex_id in ids:
                    errors.append(f"{ex_id}: ID duplicado")
                ids.add(ex_id)
                if exercise["type"] in UNGRADED_TYPES:
                    continue
                options = exercise.get("options", [])
                if options:
                    if len(set(options)) != len(options):
                        errors.append(f"{ex_id}: alternativas repetidas {options}")
                    if exercise.get("answer") not in options:
                        errors.append(f"{ex_id}: gabarito fora das opções")
                    for warning in gapped_answer_warnings(exercise):
                        warnings.append(f"{ex_id}: {warning}")
                if exercise["type"] == "sentence_order":
                    tokens = list(exercise["tokens"])
                    if exercise.get("extra_block"):
                        tokens = tokens[:-1]
                    if norm(" ".join(tokens)) != norm(exercise["answer"]):
                        errors.append(f"{ex_id}: blocos não reconstroem a frase")
                if exercise["type"] == "match_pairs":
                    rights = [pair["right"] for pair in exercise["pairs"]]
                    lefts = [pair["left"] for pair in exercise["pairs"]]
                    if len(set(rights)) != len(rights) or len(set(lefts)) != len(lefts):
                        errors.append(f"{ex_id}: pares repetidos")
        total += vocab_count

    import re as _re
    stray = _re.compile(r"[\u00ad\u200b-\u200f\ufeff\u2e80-\u9fff\u3000-\u30ff\uac00-\ud7af]")
    token = _re.compile(r"[A-Za-zÀ-ÿА-Яа-яЁё]+")
    cyrillic = _re.compile(r"[А-Яа-яЁё]")
    latin = _re.compile(r"[A-Za-zÀ-ÿ]")

    def _scan(value: object, where: str) -> None:
        if isinstance(value, str):
            found = stray.search(value)
            if found:
                errors.append(f"{where}: caractere estranho {hex(ord(found.group()))} em '…{value[max(0, found.start() - 20):found.start() + 20]}…'")
            # palavra que mistura cirílico e latino é sempre erro de digitação
            # (ex.: «дативo», com o final latino) e quebra o clicador de palavras
            for word in token.findall(value):
                if cyrillic.search(word) and latin.search(word):
                    errors.append(f"{where}: palavra com escrita mista cirílico/latino: {word!r}")
        elif isinstance(value, dict):
            for key, item in value.items():
                _scan(item, f"{where}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _scan(item, f"{where}[{index}]")

    for path in sorted(UNITS.glob("*.json")):
        try:
            _scan(json.loads(path.read_text(encoding="utf-8")), path.name)
        except Exception:
            pass
    _scan(prefix_module, PREFIX_VERBS.name)
    for path in vocab_files:
        try:
            _scan(json.loads(path.read_text(encoding="utf-8")), path.name)
        except Exception as exc:
            errors.append(f"{path.name}: JSON inválido: {exc}")

    if warnings:
        print("Avisos (respostas possivelmente óbvias ou fora do modelo):")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("Conteúdo inválido:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {len(list(UNITS.glob('*.json')))} unidades, {len(vocab_files)} lições de vocabulário, {total} exercícios, {diagnostic} diagnósticos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
