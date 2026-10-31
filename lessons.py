"""Aulas temáticas: diálogos, anúncios, leitura, foco na forma, colocações e produção.

Cada arquivo data/lessons/*.json é uma aula de um eixo temático, dividida em partes (uma sessão
cada). Formato compacto; nas alternativas, a correta vem sempre em primeiro lugar e o servidor
embaralha antes de mostrar.

    {"id": "edu1", "theme": "educacao", "order": 1, "title": "...", "title_pt": "...",
     "level": "B1–B2", "minutes": 60, "objectives": ["..."], "grammar_focus": "...",
     "parts": [{"title": "...", "goal": "...", "steps": [ETAPA, ...]}, ...]}

Etapas (t = tipo):
    warmup     {"questions": ["..."]}                                    perguntas para pensar
    vocab      {"items": [["ru", "pt", "nota"], ...]}                    apresentação + recuperação de cada item
    match      {"title", "pairs": [["esq", "dir"], ...]}                 relacionar (colocações, regência)
    dialogue   {"title", "setting", "speakers": {"Имя": "f|m|f2|m2"},
                "lines": [["Имя", "ru", "pt"]], "questions": [Q]}         escuta de diálogo em várias vozes
    listening  {"kind", "title", "voice", "text", "pt", "questions": [Q]} anúncio, notícia, recado, guia
    dictation  {"voice", "text", "pt", "hint"}                           ditado com crédito parcial
    shadow     {"voice", "lines": [["ru", "pt"]]}                        ouvir, repetir em voz alta, gravar-se
    reading    {"title", "text", "pt", "tf": [["afirmação", "V|F|N", "nota"]], "questions": [Q]}
    grammar    {"title", "paragraphs", "examples": [["ru", "pt"]], "table": {"columns", "rows"}, "pitfalls"}
    cloze      {"title", "text": "... {certa|errada|errada} ...", "bank": false, "pt", "e"}
               com "bank": true, cada lacuna é {palavra} e as opções são todas as palavras do banco
    choice     {"title", "items": [Q]}                                   prática, situações comunicativas
    order      {"title", "items": [{"a": "frase", "pt": "...", "e": "..."}]}
    fix        {"title", "items": [{"q": "frase com erro", "o": ["correção", ...], "e": "..."}]}
    produce    {"mode": "write|speak", "task", "useful": [], "model", "model_pt", "checklist": []}
    Q = {"q": "pergunta", "o": ["certa", "errada", ...], "e": "explicação"}
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

GAP = re.compile(r"\{([^{}]+)\}")
CYR = re.compile(r"[а-яё]", re.I)
STEP_LABELS = {
    "warmup": "Aquecimento", "vocab": "Vocabulário-chave", "match": "Colocações", "dialogue": "Escuta · diálogo",
    "listening": "Escuta", "dictation": "Ditado", "shadow": "Repetição em voz alta", "reading": "Leitura",
    "grammar": "Foco na forma", "cloze": "Texto com lacunas", "choice": "Prática", "order": "Montagem de frases",
    "fix": "Correção de erros", "produce": "Produção",
}
# Em que barra da gaveta cada tipo de item conta.
STEP_ASPECT = {
    "vocab": "expressoes", "match": "expressoes", "choice": "estruturas", "fix": "estruturas", "order": "estruturas",
    "cloze": "estruturas", "reading": "leitura", "dialogue": "escuta", "listening": "escuta", "dictation": "escuta",
    "shadow": "producao", "produce": "producao",
}
NOT_REVIEWED = {"produce", "shadow"}  # tarefas autoavaliadas não voltam na revisão espaçada
TF_LABELS = {"V": "Verdadeiro", "F": "Falso", "N": "Não mencionado"}
VOCAB_CHUNK = 6


def shuffled(options: list[str]) -> list[str]:
    copy = list(options)
    random.shuffle(copy)
    return copy


def has_cyrillic(text: str) -> bool:
    return bool(CYR.search(text or ""))


class LessonStore:
    def __init__(self, folder: Path):
        self.lessons: dict[str, dict] = {}
        self.by_theme: dict[str, list[str]] = {}
        self.graded: dict[str, tuple[str, int, int, int]] = {}  # item_id -> (aula, parte, etapa, subitem)
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            lesson = json.loads(path.read_text(encoding="utf-8"))
            self.lessons[lesson["id"]] = lesson
            self.by_theme.setdefault(lesson["theme"], []).append(lesson["id"])
            for p_index, part in enumerate(lesson["parts"]):
                for s_index, step in enumerate(part["steps"]):
                    for i_index in range(self.graded_count(step)):
                        self.graded[f"l:{lesson['id']}:{p_index}:{s_index}:{i_index}"] = (lesson["id"], p_index, s_index, i_index)
        for ids in self.by_theme.values():
            ids.sort(key=lambda i: (self.lessons[i].get("order", 99), i))
        self.all_vocab = [item for lesson in self.lessons.values() for part in lesson["parts"]
                          for step in part["steps"] if step["t"] == "vocab" for item in step["items"]]

    # ------------------------------------------------------------------ contagens
    @staticmethod
    def graded_count(step: dict) -> int:
        kind = step["t"]
        if kind in ("dialogue", "listening"):
            return len(step.get("questions", []))
        if kind == "reading":
            return len(step.get("tf", [])) + len(step.get("questions", []))
        if kind in ("choice", "order", "fix", "vocab"):
            return len(step.get("items", []))
        if kind in ("cloze", "match", "dictation", "produce", "shadow"):
            return 1
        return 0

    def step_of(self, item_id: str) -> dict:
        lesson, p_index, s_index, _ = self.graded[item_id]
        return self.lessons[lesson]["parts"][p_index]["steps"][s_index]

    def aspect(self, item_id: str) -> str:
        return STEP_ASPECT.get(self.step_of(item_id)["t"], "estruturas")

    def reviewable(self, item_id: str) -> bool:
        return item_id in self.graded and self.step_of(item_id)["t"] not in NOT_REVIEWED

    def theme_items(self, theme_id: str) -> list[str]:
        return [item for item, (lesson, *_rest) in self.graded.items() if self.lessons[lesson]["theme"] == theme_id]

    def label(self, item_id: str) -> tuple[str, str]:
        """Texto curto para listas (russo, português)."""
        step = self.step_of(item_id)
        _, _, _, i = self.graded[item_id]
        kind = step["t"]
        if kind == "vocab":
            return step["items"][i][0], step["items"][i][1]
        if kind in ("choice", "fix"):
            return step["items"][i]["q"], STEP_LABELS[kind]
        if kind == "order":
            return step["items"][i]["a"], step["items"][i].get("pt", "")
        if kind in ("dialogue", "listening"):
            return step["questions"][i]["q"], step.get("title") or step.get("kind", "")
        if kind == "reading":
            tf = step.get("tf", [])
            return (tf[i][0] if i < len(tf) else step["questions"][i - len(tf)]["q"]), step.get("title", "")
        if kind == "match":
            return " · ".join(p[0] for p in step["pairs"][:3]) + " …", STEP_LABELS[kind]
        return step.get("title") or step.get("task", "") or step.get("text", "")[:60], STEP_LABELS.get(kind, "")

    def summary(self, lesson_id: str, states: dict) -> dict:
        lesson = self.lessons[lesson_id]
        parts = []
        for p_index, part in enumerate(lesson["parts"]):
            items = [i for i, (l, p, _s, _i) in self.graded.items() if l == lesson_id and p == p_index]
            kinds = []
            for step in part["steps"]:
                label = STEP_LABELS.get(step["t"], "")
                if label and label not in kinds and step["t"] != "warmup":
                    kinds.append(label)
            parts.append({
                "index": p_index, "title": part["title"], "goal": part.get("goal", ""), "kinds": kinds,
                "items": len(items), "seen": sum(1 for i in items if i in states),
                "mastered": sum(1 for i in items if i in states and states[i]["stage"] >= 4),
            })
        return {
            "id": lesson_id, "title": lesson["title"], "title_pt": lesson.get("title_pt", ""), "level": lesson.get("level", ""),
            "minutes": lesson.get("minutes"), "objectives": lesson.get("objectives", []),
            "grammar_focus": lesson.get("grammar_focus", ""), "parts": parts,
            "items": sum(p["items"] for p in parts), "seen": sum(p["seen"] for p in parts),
        }

    # ------------------------------------------------------------------ telas de uma parte
    def screens(self, lesson_id: str, p_index: int, theme_id: str, token) -> list[dict]:
        """Transforma uma parte da aula em telas. ``token(payload)`` guarda o gabarito no servidor."""
        lesson = self.lessons[lesson_id]
        part = lesson["parts"][p_index]
        out: list[dict] = [{
            "type": "part_intro", "lesson_title": lesson["title"], "lesson_title_pt": lesson.get("title_pt", ""),
            "level": lesson.get("level", ""), "objectives": lesson.get("objectives", []) if p_index == 0 else [],
            "grammar_focus": lesson.get("grammar_focus", "") if p_index == 0 else "",
            "part_title": part["title"], "goal": part.get("goal", ""), "part_number": p_index + 1, "parts": len(lesson["parts"]),
        }]
        for s_index, step in enumerate(part["steps"]):
            kind = step["t"]
            label = STEP_LABELS.get(kind, "")

            def ids(i: int, s: int = s_index) -> str:
                return f"l:{lesson_id}:{p_index}:{s}:{i}"

            if kind == "warmup":
                out.append({"type": "warmup", "phase": label, "questions": step.get("questions", []), "note": step.get("note", "")})
            elif kind == "vocab":
                items = step["items"]
                for start in range(0, len(items), VOCAB_CHUNK):
                    chunk = list(range(start, min(start + VOCAB_CHUNK, len(items))))
                    out.append({"type": "vocab", "phase": label, "title": step.get("title", ""),
                                "items": [self._vocab_card(items[i]) for i in chunk]})
                    order = chunk[:]
                    random.shuffle(order)
                    out.extend(self.screen(ids(i), theme_id, token) for i in order)
            elif kind == "grammar":
                out.append({"type": "grammar", "phase": label, **{k: step.get(k) for k in ("title", "paragraphs", "examples", "table", "pitfalls")}})
            elif kind in ("dialogue", "listening"):
                out.append({"type": "listen", "phase": label, "title": step.get("title") or step.get("kind", ""),
                            "kind_label": step.get("kind", ""), "setting": step.get("setting", ""),
                            "audio_lines": self._audio_lines(step), "speakers": list(step.get("speakers", {}).keys())})
                out.extend(self.screen(ids(i), theme_id, token) for i in range(len(step.get("questions", []))))
                out.append({"type": "transcript", "phase": label, "title": step.get("title") or step.get("kind", ""),
                            "lines": self._transcript(step)})
            elif kind == "reading":
                out.extend(self.screen(ids(i), theme_id, token) for i in range(self.graded_count(step)))
                if step.get("pt"):
                    out.append({"type": "translation", "phase": label, "title": step.get("title", ""), "ru": step["text"], "pt": step["pt"]})
            else:
                out.extend(self.screen(ids(i), theme_id, token) for i in range(self.graded_count(step)))
        out.append({"type": "part_end", "lesson_id": lesson_id, "part_number": p_index + 1, "parts": len(lesson["parts"]),
                    "next_title": lesson["parts"][p_index + 1]["title"] if p_index + 1 < len(lesson["parts"]) else ""})
        return out

    @staticmethod
    def _vocab_card(item: list) -> dict:
        return {"ru": item[0], "pt": item[1], "note": item[2] if len(item) > 2 else "",
                "example": item[3] if len(item) > 3 else "", "example_pt": item[4] if len(item) > 4 else ""}

    @staticmethod
    def _audio_lines(step: dict) -> list[dict]:
        if step["t"] == "dialogue":
            voices = step.get("speakers", {})
            return [{"text": line[1], "voice": voices.get(line[0], "f")} for line in step["lines"]]
        return [{"text": step["text"], "voice": step.get("voice", "m")}]

    @staticmethod
    def _transcript(step: dict) -> list[dict]:
        if step["t"] == "dialogue":
            voices = step.get("speakers", {})
            return [{"speaker": l[0], "ru": l[1], "pt": l[2] if len(l) > 2 else "", "voice": voices.get(l[0], "f")} for l in step["lines"]]
        return [{"speaker": step.get("kind", ""), "ru": step["text"], "pt": step.get("pt", ""), "voice": step.get("voice", "m")}]

    # ------------------------------------------------------------------ uma pergunta
    def screen(self, item_id: str, theme_id: str, token) -> dict:
        lesson_id, p_index, s_index, i_index = self.graded[item_id]
        lesson = self.lessons[lesson_id]
        step = lesson["parts"][p_index]["steps"][s_index]
        kind = step["t"]
        base = {"item_id": item_id, "theme_id": theme_id, "kind": "lesson", "aspect": STEP_ASPECT.get(kind, "estruturas"),
                "phase": STEP_LABELS.get(kind, ""), "lesson_title": lesson["title"]}

        def choice(question: dict, extra: dict | None = None, instruction: str = "", exercise: str = kind) -> dict:
            correct = question["o"][0]
            options = shuffled(question["o"])
            key = token({**base, "exercise": exercise, "answer": correct, "accept": [correct],
                         "explanation": question.get("e", ""), "translation": question.get("pt", "")})
            return {**base, "type": "choice", "exercise": exercise, "token": key,
                    "instruction": instruction or step.get("title", "") or "Escolha a opção correta.",
                    "prompt": question["q"], "prompt_ru": has_cyrillic(question["q"]),
                    "options": options, "ru_options": has_cyrillic(options[0]), **(extra or {})}

        if kind == "vocab":
            item = step["items"][i_index]
            pool = [it for it in step["items"] if it is not item]
            if len(pool) < 3:
                pool += [it for it in self.all_vocab if it is not item]
            note = item[2] if len(item) > 2 else ""
            if i_index % 2 == 0:  # russo -> português
                others = list(dict.fromkeys(it[1] for it in pool if it[1] != item[1]))
                question = {"q": item[0], "o": [item[1]] + random.sample(others, min(3, len(others))), "e": note}
                return choice(question, {"audio": item[0]}, "O que significa?", "vocab")
            others = list(dict.fromkeys(it[0] for it in pool if it[0] != item[0]))
            question = {"q": item[1], "o": [item[0]] + random.sample(others, min(3, len(others))), "e": note}
            return choice(question, {}, "Como se diz em russo?", "vocab")
        if kind in ("dialogue", "listening"):
            context = {"audio_lines": self._audio_lines(step), "listen_title": step.get("title") or step.get("kind", "")}
            return choice(step["questions"][i_index], context, "Ouça quantas vezes quiser e responda.")
        if kind == "reading":
            tf = step.get("tf", [])
            context = {"context": step["text"], "context_title": step.get("title", "")}
            if i_index < len(tf):
                statement, answer, note = (list(tf[i_index]) + ["", "", ""])[:3]
                key = token({**base, "exercise": "tf", "answer": TF_LABELS[answer], "accept": [TF_LABELS[answer]], "explanation": note})
                return {**base, "type": "choice", "exercise": "tf", "token": key, "instruction": "Leia o texto e julgue a afirmação.",
                        "prompt": statement, "prompt_ru": has_cyrillic(statement),
                        "options": ["Verdadeiro", "Falso", "Não mencionado"], "keep_order": True, **context}
            return choice(step["questions"][i_index - len(tf)], context, "Leia o texto e responda.")
        if kind == "choice":
            return choice(step["items"][i_index])
        if kind == "fix":
            return choice(step["items"][i_index], {"wrong_sentence": True},
                          step.get("title") or "Esta frase tem um erro. Qual é a versão correta?")
        if kind == "order":
            item = step["items"][i_index]
            tokens = item["a"].split()
            mixed = tokens[:]
            while len(mixed) > 1 and mixed == tokens:
                random.shuffle(mixed)
            key = token({**base, "exercise": "order", "answer": item["a"], "accept": [item["a"]],
                         "explanation": item.get("e", ""), "translation": item.get("pt", "")})
            return {**base, "type": "order", "exercise": "order", "token": key, "instruction": step.get("title") or "Monte a frase.",
                    "prompt": item.get("pt", ""), "tokens": mixed}
        if kind == "cloze":
            text = step["text"]
            bank = sorted({m.group(1).split("|")[0].strip() for m in GAP.finditer(text)}, key=str.lower) if step.get("bank") else []
            parts, gaps, last = [], [], 0
            for match in GAP.finditer(text):
                parts.append(text[last:match.start()])
                options = [o.strip() for o in match.group(1).split("|")]
                gaps.append(options[0])
                parts.append({"gap": len(gaps) - 1, "options": bank if step.get("bank") else shuffled(options)})
                last = match.end()
            parts.append(text[last:])
            key = token({**base, "exercise": "cloze", "answers": gaps, "explanation": step.get("e", ""), "translation": step.get("pt", "")})
            return {**base, "type": "cloze", "exercise": "cloze", "token": key,
                    "instruction": step.get("title") or "Complete o texto.", "bank": bank, "parts": parts}
        if kind == "match":
            pairs = step["pairs"]
            key = token({**base, "exercise": "match", "pairs": {p[0]: p[1] for p in pairs}, "explanation": step.get("e", "")})
            return {**base, "type": "match", "exercise": "match", "token": key, "instruction": step.get("title") or "Relacione.",
                    "left": shuffled([p[0] for p in pairs]), "right": shuffled([p[1] for p in pairs])}
        if kind == "dictation":
            key = token({**base, "exercise": "dictation", "answer": step["text"], "accept": [step["text"]], "typed": True,
                         "translation": step.get("pt", "")})
            return {**base, "type": "input", "exercise": "dictation", "token": key, "instruction": "Ouça e escreva exatamente o que foi dito.",
                    "audio_lines": [{"text": step["text"], "voice": step.get("voice", "f")}], "prompt": step.get("hint", ""), "long": True}
        if kind == "shadow":
            key = token({**base, "exercise": "shadow", "answer": "", "self_rated": True})
            lines = [{"ru": l[0], "pt": l[1] if len(l) > 1 else "", "voice": step.get("voice", "f")} for l in step["lines"]]
            return {**base, "type": "shadow", "exercise": "shadow", "token": key, "instruction": step.get("title") or
                    "Ouça cada frase e repita em voz alta, imitando o ritmo e a entonação.", "lines": lines}
        if kind == "produce":
            key = token({**base, "exercise": "produce", "answer": step.get("model", ""), "checklist": step.get("checklist", [])})
            return {**base, "type": "produce", "exercise": "produce", "mode": step.get("mode", "write"), "token": key,
                    "instruction": "Produção oral" if step.get("mode") == "speak" else "Produção escrita",
                    "prompt": step["task"], "useful": step.get("useful", []), "model": step.get("model", ""),
                    "model_pt": step.get("model_pt", ""), "checklist": step.get("checklist", []), "min_words": step.get("min_words", 0)}
        raise ValueError(f"Etapa sem pergunta: {kind}")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower().replace("ё", "е").replace("́", ""))


def grade_cloze(pending: dict, answers: list) -> tuple[float, list[bool]]:
    expected = pending["answers"]
    marks = [i < len(answers) and norm(answers[i]) == norm(e) for i, e in enumerate(expected)]
    return (sum(marks) / len(marks) if marks else 0.0), marks


def grade_match(pending: dict, given: list) -> tuple[float, dict]:
    pairs = pending["pairs"]
    chosen = {str(p.get("left")): str(p.get("right")) for p in given if isinstance(p, dict)}
    right = sum(1 for left, target in pairs.items() if chosen.get(left) == target)
    return right / len(pairs), pairs


def validate(lesson: dict, theme_ids: set[str]) -> list[str]:
    """Erros de forma numa aula (usado por tools/validate_content.py)."""
    errors: list[str] = []
    lid = lesson.get("id", "?")
    if lesson.get("theme") not in theme_ids:
        errors.append(f"{lid}: tema desconhecido {lesson.get('theme')}")
    for p_index, part in enumerate(lesson.get("parts", [])):
        for s_index, step in enumerate(part.get("steps", [])):
            where = f"{lid} parte {p_index + 1} etapa {s_index + 1} ({step.get('t')})"
            kind = step.get("t")
            if kind not in STEP_LABELS:
                errors.append(f"{where}: tipo desconhecido")
                continue
            questions = (list(step.get("questions", [])) if kind != "warmup" else []) + (list(step.get("items", [])) if kind in ("choice", "fix") else [])
            for q in questions:
                options = q.get("o", [])
                if len(options) < 2 or len(set(options)) != len(options):
                    errors.append(f"{where}: alternativas ausentes ou repetidas em «{q.get('q', '')[:40]}»")
            if kind == "dialogue":
                speakers = step.get("speakers", {})
                for line in step.get("lines", []):
                    if line[0] not in speakers:
                        errors.append(f"{where}: falante sem voz: {line[0]}")
                    if speakers.get(line[0]) not in ("f", "m", "f2", "m2"):
                        errors.append(f"{where}: voz inválida para {line[0]}")
                    if len(line[1]) > 780:
                        errors.append(f"{where}: fala longa demais para o áudio")
            if kind in ("listening", "dictation") and len(step.get("text", "")) > 780:
                errors.append(f"{where}: texto longo demais para o áudio")
            if kind == "shadow":
                for line in step.get("lines", []):
                    if len(line[0]) > 780:
                        errors.append(f"{where}: frase longa demais para o áudio")
            if kind == "reading":
                for tf in step.get("tf", []):
                    if len(tf) < 2 or tf[1] not in TF_LABELS:
                        errors.append(f"{where}: afirmação V/F/N mal formada")
            if kind == "cloze":
                gaps = GAP.findall(step.get("text", ""))
                if not gaps:
                    errors.append(f"{where}: lacunas ausentes")
                for gap in gaps:
                    options = [o.strip() for o in gap.split("|")]
                    if not step.get("bank") and (len(options) < 2 or len(set(options)) != len(options)):
                        errors.append(f"{where}: lacuna sem alternativas: {gap}")
            if kind == "match":
                pairs = step.get("pairs", [])
                if len({p[0] for p in pairs}) != len(pairs) or len({p[1] for p in pairs}) != len(pairs):
                    errors.append(f"{where}: pares repetidos")
            if kind == "order":
                for item in step.get("items", []):
                    if len(item.get("a", "").split()) < 3:
                        errors.append(f"{where}: frase curta demais para montar")
            if kind == "vocab":
                items = step.get("items", [])
                if len({i[0] for i in items}) != len(items) or len({i[1] for i in items}) != len(items):
                    errors.append(f"{where}: vocabulário repetido")
    return errors
