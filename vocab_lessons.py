"""Lições de vocabulário «Лексика в диалоге» (página Vocabulário, só russo).

Cada arquivo de ``data/vocab_lessons`` descreve uma cena: um diálogo com vozes
diferentes e oito construções da unidade correspondente. A partir dessa
descrição, este módulo gera os exercícios de forma determinística (IDs
estáveis, para que a revisão espaçada reencontre o mesmo item) e monta a
sessão na ordem pedagógica descrita em ``docs/modelo_licao_vocabulario.md``:

1. ouvir o diálogo antes de estudar (pré-teste + escuta global);
2. cartão → reconhecer o sentido → escolher a forma, com intervalos crescentes;
3. lacuna, compreensão auditiva e montagem, sempre em frases novas;
4. volta ao diálogo: detalhes, reconstrução, responder à fala, re-escuta;
5. produção escrita curta.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path


VOCAB_UNIT_PREFIX = "vocab_"
# Tipos que não são corrigidos: servem de apresentação e nunca vão ao /api/answer.
UNGRADED_TYPES = {"vocab_card", "dialogue_review"}
PARTS = {
    "1": "Ouvir e apresentar",
    "2": "Praticar em contexto",
    "3": "Voltar ao diálogo e produzir",
}


def _stable_rng(*seed: object) -> random.Random:
    return random.Random("|".join(str(part) for part in seed))


def _tokens(sentence: str) -> list[str]:
    return [token for token in sentence.split() if token]


class VocabLessonStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lessons: list[dict] = []
        self.lessons_by_id: dict[str, dict] = {}
        self.exercises: dict[str, dict] = {}
        # exercise_id → unidade sintética (mesma forma que ContentStore usa)
        self.exercise_unit: dict[str, dict] = {}

    # ------------------------------------------------------------------ carga
    def load(self) -> None:
        lessons: list[dict] = []
        exercises: dict[str, dict] = {}
        exercise_unit: dict[str, dict] = {}
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.json")):
                with path.open(encoding="utf-8") as handle:
                    lesson = json.load(handle)
                self._check(lesson, path.name)
                lesson["unit_key"] = VOCAB_UNIT_PREFIX + lesson["id"]
                generated = self._generate(lesson)
                synthetic_unit = {
                    "id": lesson["unit_key"],
                    "title": f"Vocabulário · {lesson['title']}",
                    "course_id": "russian",
                    "exercises": generated,
                }
                for exercise in generated:
                    if exercise["id"] in exercises:
                        raise ValueError(f"{path.name}: ID duplicado {exercise['id']}")
                    exercises[exercise["id"]] = exercise
                    exercise_unit[exercise["id"]] = synthetic_unit
                lesson["generated"] = generated
                lessons.append(lesson)
        self.lessons = sorted(lessons, key=lambda item: item.get("order", 999))
        self.lessons_by_id = {lesson["id"]: lesson for lesson in self.lessons}
        self.exercises = exercises
        self.exercise_unit = exercise_unit

    @staticmethod
    def _check(lesson: dict, name: str) -> None:
        required = {"id", "unit_id", "title", "speakers", "dialogue", "items"}
        missing = required - lesson.keys()
        if missing:
            raise ValueError(f"{name}: campos ausentes: {sorted(missing)}")
        lines = lesson["dialogue"].get("lines", [])
        for index, line in enumerate(lines):
            if line.get("speaker") not in lesson["speakers"]:
                raise ValueError(f"{name}: fala {index} com falante desconhecido")
        for rec in lesson.get("reconstruct", []):
            line = lines[rec["line"]]
            if rec["gap"] not in line["ru"]:
                raise ValueError(f"{name}: lacuna «{rec['gap']}» não está na fala {rec['line']}")
        keys = set()
        for item in lesson["items"]:
            if item["key"] in keys:
                raise ValueError(f"{name}: chave repetida {item['key']}")
            keys.add(item["key"])
            cloze = item["cloze"]
            if "___" not in cloze["ru"]:
                raise ValueError(f"{name}: {item['key']}: lacuna sem ___")
            extra = item["example"].get("extra")
            if extra and extra in _tokens(item["example"]["ru"]):
                raise ValueError(f"{name}: {item['key']}: bloco extra já existe na frase")

    # --------------------------------------------------------------- geração
    def voice_of(self, lesson: dict, speaker: str) -> str:
        return lesson["speakers"].get(speaker, "f")

    def _public_lines(self, lesson: dict) -> list[dict]:
        return [
            {
                "speaker": line["speaker"],
                "voice": self.voice_of(lesson, line["speaker"]),
                "ru": line["ru"],
                "pt": line.get("pt", ""),
            }
            for line in lesson["dialogue"]["lines"]
        ]

    def _generate(self, lesson: dict) -> list[dict]:
        lid = lesson["id"]
        unit_key = lesson["unit_key"]
        items = lesson["items"]
        lines = self._public_lines(lesson)
        base_tags = ["vocabulário em diálogo", f"lição {lid}"]
        generated: list[dict] = []

        def add(exercise: dict) -> None:
            exercise.setdefault("difficulty", 2)
            exercise.setdefault("tags", [])
            exercise["unit_id"] = unit_key
            exercise["lesson_id"] = lid
            exercise["speak_options"] = False
            generated.append(exercise)

        dialogue_payload = {
            "dialogue_title": lesson["dialogue"].get("title", lesson["title"]),
            "setting": lesson["dialogue"].get("setting", ""),
            "lines": lines,
            "highlights": highlight_stems(lesson),
        }

        for index, question in enumerate(lesson.get("gist", []), start=1):
            add({
                "id": f"vx-{lid}-gist-{index}",
                "type": "dialogue",
                "stage": "comprehension",
                "vx_role": "gist",
                "phase": "1 · OUVIR ANTES DE ESTUDAR",
                "instruction": "Ouça o diálogo inteiro antes de ver o vocabulário. Entender a ideia geral basta: errar aqui prepara a atenção para o que vem depois.",
                "prompt": question["prompt"],
                "options": question["options"],
                "answer": question["answer"],
                "explanation": question.get("explanation", ""),
                "tags": base_tags + ["аудирование", "sentido geral"],
                **dialogue_payload,
            })

        for position, item in enumerate(items):
            key = item["key"]
            lemma_tag = f"lexeme:{item['lemma']}"
            item_tags = base_tags + [item.get("tag") or item["lemma"], lemma_tag]
            case_tag = item.get("case")
            if case_tag:
                item_tags.append(case_tag)
            example = item["example"]

            add({
                "id": f"vx-{lid}-{key}-card",
                "type": "vocab_card",
                "stage": "presentation",
                "phase": "2 · APRESENTAR",
                "instruction": "Ouça, repita em voz alta e observe a regência. Depois o cartão some e você terá de recuperá-lo.",
                "prompt": item["head"],
                "head": item["head"],
                "regency": item.get("regency", ""),
                "case": item.get("case", ""),
                "meaning": item["pt"],
                "chunk": item["chunk"],
                "chunk_pt": item["chunk_pt"],
                "example_ru": example["ru"],
                "example_pt": example["pt"],
                "trap": item.get("trap", ""),
                "tags": item_tags,
            })

            # Distratores de sentido: as outras construções da lição com
            # tradução de comprimento parecido, para que o tamanho da
            # alternativa não entregue a resposta.
            rng = _stable_rng(lid, key, "mean")
            others = sorted(
                (other for other in items if other["key"] != key),
                key=lambda other: abs(len(other["chunk_pt"]) - len(item["chunk_pt"])) + rng.random() * 6,
            )
            add({
                "id": f"vx-{lid}-{key}-mean",
                "type": "listening",
                "stage": "recognition",
                "phase": "2 · RECONHECER",
                "instruction": "Ouça a construção (sem texto) e escolha o sentido.",
                "prompt": "O que significa a construção que você ouviu?",
                "audio_text": item["chunk"],
                "options": [item["chunk_pt"]] + [other["chunk_pt"] for other in others[:3]],
                "answer": item["chunk_pt"],
                "explanation": f"{item['chunk']} — {item['chunk_pt']}. {item.get('regency', '')}".strip(),
                "after_audio": {"text": item["chunk"], "voice": "f"},
                "tags": item_tags + ["recuperação receptiva"],
            })

            add({
                "id": f"vx-{lid}-{key}-form",
                "type": "choice",
                "stage": "recall",
                "phase": "2 · RECUPERAR A FORMA",
                "instruction": "Escolha a construção russa exata. As alternativas diferem na preposição, no caso ou na terminação.",
                "prompt": f"«{item['chunk_pt']}»",
                "options": [item["chunk"]] + list(item["chunk_wrong"]),
                "answer": item["chunk"],
                "explanation": f"{item.get('regency', '')}. {item.get('form_note', '')}".strip(" ."),
                "after_audio": {"text": item["chunk"], "voice": "m"},
                "tags": item_tags + ["recuperação produtiva"],
                "difficulty": 3,
            })

            cloze = item["cloze"]
            add({
                "id": f"vx-{lid}-{key}-cloze",
                "type": "choice",
                "stage": "context",
                "phase": "3 · CONTEXTO",
                "instruction": "Complete a frase nova com a forma exata: preposição, caso e número.",
                "prompt": cloze["ru"],
                "options": [cloze["answer"]] + list(cloze["wrong"]),
                "answer": cloze["answer"],
                "explanation": " ".join(filter(None, [cloze.get("note", ""), f"Tradução: {cloze.get('pt', '')}" if cloze.get("pt") else ""])),
                "after_audio": {"text": cloze["ru"].replace("___", cloze["answer"]), "voice": "f"},
                "tags": item_tags + ["lacuna"],
                "difficulty": 3,
            })

            hear = item["hear"]
            add({
                "id": f"vx-{lid}-{key}-hear",
                "type": "listening",
                "stage": "comprehension",
                "phase": "3 · OUVIR E ENTENDER",
                "instruction": "Ouça a frase e escolha a tradução fiel. Atenção a quem faz o quê: os casos decidem.",
                "prompt": "O que a frase diz exatamente?",
                "audio_text": hear["ru"],
                "voice": "m" if position % 2 else "f",
                "options": [hear["pt"]] + list(hear["wrong"]),
                "answer": hear["pt"],
                "explanation": hear.get("note", ""),
                "tags": item_tags + ["аудирование"],
                "difficulty": 3,
            })

            tokens = _tokens(example["ru"])
            extra = example.get("extra")
            add({
                "id": f"vx-{lid}-{key}-build",
                "type": "sentence_order",
                "stage": "construction",
                "phase": "3 · MONTAR",
                "instruction": "Monte a frase do cartão. Sobra um bloco: ele tem a terminação ou a preposição errada." if extra else "Monte a frase do cartão.",
                "prompt": f"«{example['pt']}»",
                "tokens": tokens + ([extra] if extra else []),
                "extra_block": bool(extra),
                "answer": example["ru"],
                "explanation": example.get("note", item.get("regency", "")),
                "after_audio": {"text": example["ru"], "voice": "m"},
                "tags": item_tags + ["produção de frase"],
                "difficulty": 3,
            })

        for index, question in enumerate(lesson.get("detail", []), start=1):
            add({
                "id": f"vx-{lid}-detail-{index}",
                "type": "dialogue",
                "stage": "comprehension",
                "vx_role": "detail",
                "phase": "4 · OUVIR DE NOVO",
                "instruction": "Agora que você conhece as construções, ouça o diálogo de novo e responda ao detalhe.",
                "prompt": question["prompt"],
                "options": question["options"],
                "answer": question["answer"],
                "explanation": question.get("explanation", ""),
                "tags": base_tags + ["аудирование", "detalhe"],
                "difficulty": 3,
                **dialogue_payload,
            })

        for index, rec in enumerate(lesson.get("reconstruct", []), start=1):
            line = lines[rec["line"]]
            previous = lines[rec["line"] - 1] if rec["line"] > 0 else None
            add({
                "id": f"vx-{lid}-rec-{index}",
                "type": "choice",
                "stage": "reconstruction",
                "phase": "4 · RECONSTRUIR O DIÁLOGO",
                "instruction": "Complete a fala do diálogo como foi dita.",
                "context": f"{previous['speaker']}: {previous['ru']}" if previous else "",
                "prompt": f"{line['speaker']}: {line['ru'].replace(rec['gap'], '___', 1)}",
                "options": [rec["gap"]] + list(rec["wrong"]),
                "answer": rec["gap"],
                "explanation": rec.get("note", ""),
                "after_audio": {"text": line["ru"], "voice": line["voice"]},
                "tags": base_tags + ["reconstrução"] + rec.get("tags", []),
                "difficulty": 3,
            })

        match = lesson.get("match")
        if match:
            add({
                "id": f"vx-{lid}-match",
                "type": "match_pairs",
                "stage": "meaning",
                "phase": "3 · COLOCAÇÕES",
                "instruction": match.get("instruction", "Relacione cada verbo ao complemento que ele rege."),
                "prompt": match.get("prompt", "Qual complemento combina com cada verbo?"),
                "pairs": match["pairs"],
                "left_items": [pair["left"] for pair in match["pairs"]],
                "right_items": _stable_shuffled([pair["right"] for pair in match["pairs"]], lid),
                "explanation": match.get("explanation", ""),
                "tags": base_tags + ["colocações"],
            })

        for index, reply in enumerate(lesson.get("replies", []), start=1):
            add({
                "id": f"vx-{lid}-reply-{index}",
                "type": "listening",
                "stage": "transfer",
                "phase": "4 · RESPONDER À FALA",
                "instruction": f"Você é {reply['you']}. Ouça {reply['speaker']} e escolha a resposta adequada e gramaticalmente correta.",
                "prompt": reply.get("prompt", "Qual é a melhor resposta?"),
                "audio_text": reply["ru"],
                "voice": self.voice_of(lesson, reply["speaker"]) if reply["speaker"] in lesson["speakers"] else "m",
                "options": [reply["answer"]] + list(reply["wrong"]),
                "answer": reply["answer"],
                "explanation": reply.get("explanation", ""),
                "after_audio": {"text": reply["answer"], "voice": self.voice_of(lesson, reply["you"]) if reply["you"] in lesson["speakers"] else "f"},
                "tags": base_tags + ["говорение", "réplica"],
                "difficulty": 3,
            })

        add({
            "id": f"vx-{lid}-review",
            "type": "dialogue_review",
            "stage": "fluency",
            "phase": "5 · RE-ESCUTA",
            "instruction": "Ouça o diálogo inteiro acompanhando o texto. As construções da lição estão destacadas; toque em uma fala para ouvi-la sozinha.",
            "prompt": lesson["dialogue"].get("title", lesson["title"]),
            "tags": base_tags,
            **dialogue_payload,
        })

        writing = lesson.get("writing")
        if writing:
            add({
                "id": f"vx-{lid}-write",
                "type": "open_text",
                "stage": "micro_writing",
                "phase": "6 · PRODUZIR",
                "instruction": f"Escreva {writing.get('words', '40–60')} palavras. Use pelo menos três destas construções: {' · '.join(writing['use'])}.",
                "prompt": writing["prompt"],
                "review_notes": writing.get("notes", ""),
                "tags": base_tags + ["produção escrita"],
            })
        return generated

    # --------------------------------------------------------------- sessões
    def lesson_parts(self, lesson: dict) -> dict[str, list[dict]]:
        lookup = {exercise["id"]: exercise for exercise in lesson["generated"]}
        lid = lesson["id"]
        keys = [item["key"] for item in lesson["items"]]

        gist = [lookup[f"vx-{lid}-gist-{i}"] for i in range(1, len(lesson.get("gist", [])) + 1)]

        # Parte 1: cartões com recuperações em intervalos crescentes
        # (Pimsleur/expanding retrieval). Cada item i: cartão em 3i, sentido
        # duas telas depois e forma cerca de cinco telas depois do cartão.
        events: list[tuple[float, int, dict]] = []
        for index, key in enumerate(keys):
            events.append((3 * index, 0, lookup[f"vx-{lid}-{key}-card"]))
            events.append((3 * index + 2, 1, lookup[f"vx-{lid}-{key}-mean"]))
            events.append((3 * index + 6.5, 2, lookup[f"vx-{lid}-{key}-form"]))
        presentation = [exercise for _, _, exercise in sorted(events, key=lambda item: (item[0], item[1]))]

        # Parte 2: três tipos em rodízio, com o mesmo item nunca em telas vizinhas.
        order = keys[:]
        random.shuffle(order)
        size = len(order)
        practice: list[dict] = []
        for position in range(size):
            practice.append(lookup[f"vx-{lid}-{order[position]}-cloze"])
            practice.append(lookup[f"vx-{lid}-{order[(position + 3) % size]}-hear"])
            practice.append(lookup[f"vx-{lid}-{order[(position + 5) % size]}-build"])
        if f"vx-{lid}-match" in lookup:
            practice.append(lookup[f"vx-{lid}-match"])

        closing = [lookup[f"vx-{lid}-detail-{i}"] for i in range(1, len(lesson.get("detail", [])) + 1)]
        closing += [lookup[f"vx-{lid}-rec-{i}"] for i in range(1, len(lesson.get("reconstruct", [])) + 1)]
        closing += [lookup[f"vx-{lid}-reply-{i}"] for i in range(1, len(lesson.get("replies", [])) + 1)]
        closing.append(lookup[f"vx-{lid}-review"])
        if f"vx-{lid}-write" in lookup:
            closing.append(lookup[f"vx-{lid}-write"])
        return {"1": gist + presentation, "2": practice, "3": closing}

    def session(self, lesson_id: str, part: str = "all") -> list[dict]:
        lesson = self.lessons_by_id.get(lesson_id)
        if not lesson:
            return []
        parts = self.lesson_parts(lesson)
        if part in parts:
            return [dict(exercise) for exercise in parts[part]]
        return [dict(exercise) for key in ("1", "2", "3") for exercise in parts[key]]

    def public_lesson(self, lesson: dict, with_dialogue: bool = False) -> dict:
        graded = [ex for ex in lesson["generated"] if ex["type"] not in UNGRADED_TYPES and ex["type"] != "open_text"]
        parts = self.lesson_parts(lesson)
        data = {
            "id": lesson["id"],
            "unit_id": lesson["unit_id"],
            "order": lesson.get("order", 999),
            "title": lesson["title"],
            "theme": lesson.get("theme", ""),
            "description": lesson.get("description", ""),
            "setting": lesson["dialogue"].get("setting", ""),
            "dialogue_title": lesson["dialogue"].get("title", lesson["title"]),
            "item_heads": [item["head"] for item in lesson["items"]],
            "graded_count": len(graded),
            "screens": {key: len(value) for key, value in parts.items()},
            "parts": PARTS,
        }
        if with_dialogue:
            data["items"] = [
                {
                    "head": item["head"],
                    "regency": item.get("regency", ""),
                    "case": item.get("case", ""),
                    "pt": item["pt"],
                    "chunk": item["chunk"],
                    "chunk_pt": item["chunk_pt"],
                }
                for item in lesson["items"]
            ]
            data["lines"] = self._public_lines(lesson)
            data["highlights"] = highlight_stems(lesson)
            data["speakers"] = lesson["speakers"]
        return data


def highlight_stems(lesson: dict) -> list[str]:
    """Radicais das palavras-alvo, para destacar no texto do diálogo.

    O diálogo usa formas flexionadas (привыкнешь, приведёт, помогла); o
    radical de até cinco letras de cada verbo/palavra do cabeçalho as
    reconhece sem precisar de um analisador morfológico. O cliente pode
    acrescentar ``extra_highlights`` quando o radical não basta.
    """
    stems: set[str] = set()
    for item in lesson["items"]:
        words = re.findall(r"[А-Яа-яЁё]+", item["head"]) + list(item.get("highlight", []))
        for word in words:
            word = word.lower().replace("ё", "е")
            if len(word) < 4 or word in {"быть", "себя", "кому", "чему", "чего", "кого", "кем", "чем"}:
                continue
            for suffix in ("ться", "тись", "ть", "ти", "чь"):
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    stems.add(word[: -len(suffix)][:5])
                    break
            else:
                stems.add(word[: len(word) - 1] if len(word) <= 5 else word[:5])
    return sorted(stems)


def _stable_shuffled(values: list[str], seed: str) -> list[str]:
    copy = list(values)
    _stable_rng(seed, "match").shuffle(copy)
    return copy


def gapped_answer_warnings(exercise: dict) -> list[str]:
    """Heurísticas de «resposta óbvia» usadas pelo validador."""
    warnings: list[str] = []
    options = [str(option) for option in exercise.get("options", [])]
    answer = str(exercise.get("answer", ""))
    if len(options) >= 3 and answer in options:
        lengths = sorted((len(option), option) for option in options)
        longest_len, longest = lengths[-1]
        second_len = lengths[-2][0]
        if longest == answer and longest_len > 1.35 * max(1, second_len) and longest_len - second_len > 6:
            warnings.append("gabarito é a alternativa visivelmente mais longa")
        shortest_len, shortest = lengths[0]
        if shortest == answer and lengths[1][0] > 1.6 * max(1, shortest_len) and lengths[1][0] - shortest_len > 8:
            warnings.append("gabarito é a alternativa visivelmente mais curta")
    cyr = re.compile(r"[А-Яа-яЁё]")
    if options and answer in options:
        scripts = {bool(cyr.search(option)) for option in options}
        if len(scripts) > 1:
            warnings.append("alternativas misturam russo e português")
    return warnings
