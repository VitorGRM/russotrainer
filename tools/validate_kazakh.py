"""Valida as aulas do curso de cazaque (data/kz/lessons/*.json) e o motor que as serve.

Formato de uma aula:
    {"id": "k01", "n": 1, "level": "A1.0", "module": "...", "title": "...", "kz": "...", "goal": "...",
     "rules": [{"title", "points": [...], "ex": [[kz, pt]], "trap"}],
     "sounds": [{"l": "Ә ә", "pt": "...", "words": [[kz, pt]]}],            # opcional (módulo 0)
     "vocab": [[kz, pt] ou [kz, pt, nota]],
     "dialog": {"title", "lines": [["A"|"B", kz, pt]]},
     "reading": {"title", "paragraphs": [[kz, pt]]},                         # opcional
     "items": [EXERCÍCIO]}
Exercícios (campo "t"): mc e listen (a, w[3], listen tem audio), gap (q com ___, a[...]), type (q, a[...]),
transform (p, q, a[...]), order (a sem pontuação, x = intrusas), pairs (p = [[esq, dir]...]), dict (a).
Categorias ("c"): F H P C V S L U R (ver kazakh.CATEGORIES).

    python tools/validate_kazakh.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kazakh import CATEGORIES, KazakhContent, KazakhCourse, all_audio_texts  # noqa: E402

MIXED = re.compile(r"[A-Za-z][Ѐ-ӿ]|[Ѐ-ӿ][A-Za-z]")
TYPES = {"mc", "listen", "gap", "type", "transform", "order", "pairs", "dict"}


def check() -> list[str]:
    errors: list[str] = []
    lessons = []
    for path in sorted((ROOT / "data" / "kz" / "lessons").glob("*.json")):
        try:
            lessons += json.loads(path.read_text(encoding="utf-8"))["lessons"]
        except (json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{path.name}: JSON inválido ({exc})")
    ids, item_ids = set(), set()
    numbers = sorted(l.get("n", 0) for l in lessons)
    if numbers != list(range(1, len(lessons) + 1)):
        errors.append(f"As aulas devem ser numeradas de 1 a {len(lessons)} sem buracos: {numbers}")

    def text_ok(where: str, text: str) -> None:
        if MIXED.search(text):
            errors.append(f"{where}: letra latina misturada com cirílica em «{text}»")

    for lesson in lessons:
        lid = lesson.get("id", "?")
        if lid in ids:
            errors.append(f"{lid}: id repetido")
        ids.add(lid)
        for key in ("n", "level", "module", "title", "kz", "goal", "rules", "vocab", "items"):
            if not lesson.get(key):
                errors.append(f"{lid}: falta «{key}»")
        for rule in lesson.get("rules", []):
            if not rule.get("title") or not rule.get("points"):
                errors.append(f"{lid}: regra sem título ou sem pontos")
            for ex in rule.get("ex", []):
                if len(ex) != 2:
                    errors.append(f"{lid}: exemplo deve ser [cazaque, português]: {ex}")
                else:
                    text_ok(lid, ex[0])
        for sound in lesson.get("sounds", []):
            if not sound.get("l") or not sound.get("words"):
                errors.append(f"{lid}: som incompleto {sound}")
        for entry in lesson.get("vocab", []):
            if len(entry) not in (2, 3) or not all(entry[:2]):
                errors.append(f"{lid}: vocabulário deve ser [cazaque, português(, nota)]: {entry}")
            else:
                text_ok(lid, entry[0])
        if len(lesson.get("vocab", [])) < 8:
            errors.append(f"{lid}: vocabulário curto demais ({len(lesson.get('vocab', []))})")
        for line in (lesson.get("dialog") or {}).get("lines", []):
            if len(line) != 3 or line[0] not in ("A", "B"):
                errors.append(f"{lid}: fala de diálogo deve ser [A|B, cazaque, português]: {line}")
            else:
                text_ok(lid, line[1])
        for para in (lesson.get("reading") or {}).get("paragraphs", []):
            if len(para) != 2:
                errors.append(f"{lid}: parágrafo deve ser [cazaque, português]")
        items = lesson.get("items", [])
        if len(items) < 10:
            errors.append(f"{lid}: poucos exercícios ({len(items)})")
        for item in items:
            iid = item.get("id", "?")
            where = f"{lid}/{iid}"
            if not iid.startswith(lid + "-"):
                errors.append(f"{where}: o id do exercício deve começar por «{lid}-»")
            if iid in item_ids:
                errors.append(f"{where}: id repetido")
            item_ids.add(iid)
            t = item.get("t")
            if t not in TYPES:
                errors.append(f"{where}: tipo desconhecido {t}")
                continue
            if item.get("c") not in CATEGORIES:
                errors.append(f"{where}: categoria inválida {item.get('c')}")
            if not item.get("e"):
                errors.append(f"{where}: falta a explicação «e»")
            for field in ("q", "audio"):
                if isinstance(item.get(field), str):
                    text_ok(where, item[field])
            answers = item.get("a") if isinstance(item.get("a"), list) else [item.get("a")]
            for a in answers:
                if isinstance(a, str):
                    text_ok(where, a)
            if t in ("mc", "listen"):
                wrong = item.get("w", [])
                if not isinstance(item.get("a"), str) or len(wrong) != 3:
                    errors.append(f"{where}: escolha precisa de «a» e 3 distratores em «w»")
                elif item["a"] in wrong or len(set(wrong)) != 3:
                    errors.append(f"{where}: distratores repetidos ou iguais à resposta")
                if t == "listen" and not item.get("audio"):
                    errors.append(f"{where}: escuta sem «audio»")
            elif t == "gap":
                if "___" not in item.get("q", "") or not isinstance(item.get("a"), list):
                    errors.append(f"{where}: lacuna precisa de ___ em «q» e lista em «a»")
            elif t in ("type", "transform"):
                if not isinstance(item.get("a"), list) or not item.get("q"):
                    errors.append(f"{where}: «{t}» precisa de «q» e lista em «a»")
                if t == "transform" and not item.get("p"):
                    errors.append(f"{where}: transformação sem instrução «p»")
            elif t == "order":
                if re.search(r"[.,!?—«»:;]", item.get("a", "")):
                    errors.append(f"{where}: frase de montar não deve ter pontuação: «{item.get('a')}»")
                if not item.get("x"):
                    errors.append(f"{where}: montar frase precisa de uma palavra intrusa em «x»")
                if set(item.get("x", [])) & set(item.get("a", "").split()):
                    errors.append(f"{where}: a intrusa também está na frase")
            elif t == "pairs":
                pairs = item.get("p", [])
                if len(pairs) < 3 or len({p[0] for p in pairs}) != len(pairs) or len({p[1] for p in pairs}) != len(pairs):
                    errors.append(f"{where}: pares precisam de 3+ itens sem repetição")
            elif t == "dict":
                if not item.get("a"):
                    errors.append(f"{where}: ditado sem frase")
    return errors


def smoke() -> list[str]:
    """Monta cada sessão e responde a todos os exercícios de uma aula, como o app faria."""
    errors: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # o SQLite pode segurar o arquivo no Windows
        course = KazakhCourse(ROOT / "data" / "kz", Path(tmp) / "t.sqlite3")
        course.set_free_mode(True)
        for lesson_id in course.content.order:
            for mode in ("learn", "challenge", "vocab"):
                try:
                    session = course.lesson_session(lesson_id, mode)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{lesson_id}/{mode}: {exc}")
                    continue
                for step in session["steps"]:
                    if "token" not in step:
                        continue
                    pend = course.pending[step["token"]]
                    answer = [{"left": a, "right": b} for a, b in pend["pairs"]] if "pairs" in pend else pend["answer"]
                    result = course.answer({"token": step["token"], "answer": answer, "mode": mode})
                    if not result.get("correct"):
                        errors.append(f"{step['item_id']}: a própria resposta não foi aceita")
        if not all_audio_texts(course.content):
            errors.append("nenhum texto de áudio encontrado")
    return errors


if __name__ == "__main__":
    problems = check()
    if not problems:
        problems = smoke()
    for problem in problems:
        print("ERRO", problem)
    if problems:
        sys.exit(1)
    data = KazakhContent(ROOT / "data" / "kz")
    print(f"OK: {len(data.lessons)} aulas, {len(data.items)} exercícios, {len(data.words)} palavras.")
