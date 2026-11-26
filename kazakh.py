"""Curso de cazaque (A1 → B1): 40 aulas sequenciais, do som das letras ao B1.

O conteúdo fica em data/kz/lessons/*.json ({"lessons": [AULA, ...]}; ver tools/validate_kazakh.py).
Cada aula tem explicação (com narração em português), sons (módulo 0), vocabulário, diálogo em duas
vozes, texto de leitura (aulas finais) e exercícios. A aula N+1 abre quando a aula N foi concluída
(todos os exercícios respondidos), a não ser que o "modo livre" esteja ligado.

Mesma filosofia do curso de francês: errar não custa nada. O erro abre uma pista e uma nova tentativa,
o XP nunca diminui e o item errado volta algumas telas depois. A correção reconhece quando o aluno
trocou uma letra cazaque pela parecida do russo (қ/к, ү/у, і/и…) e avisa isso em vez de dar "errado".

O progresso fica nas tabelas kz_* do mesmo banco (FrenchProgress com prefixo "kz").
"""

from __future__ import annotations

import difflib
import json
import random
import re
import secrets
import threading
from pathlib import Path

from french import (MASTERED_STAGE, SCORE_BY_TRY, XP_BY_TRY, XP_FAIL, XP_INTRO, XP_RECOVERY,
                    FrenchProgress, dictation_marks, first_sentence, grade_pairs, iso, norm, shuffled)

CATEGORIES = {
    "F": "Sons e escrita",
    "H": "Harmonia e sufixos",
    "P": "Pessoa e possessivo",
    "C": "Casos",
    "V": "Verbos",
    "S": "Ordem e frase",
    "L": "Vocabulário",
    "U": "Uso e situação",
    "R": "Leitura",
}
SIGNALS = {
    "F": "Quase. Confira as letras próprias do cazaque: ә ө ү ұ і қ ғ ң һ.",
    "H": "Quase. Confira a harmonia: palavra dura (а о ұ ы) pede sufixo com а/ы; branda (ә е ө ү і), com е/і. E veja a última letra: vogal, sonora ou surda?",
    "P": "Quase. Confira a terminação de pessoa ou o possessivo (-м, -ң, -ңыз, -ы/-сы…).",
    "C": "Quase. Confira o caso: onde (-да), para onde (-ға), de onde (-дан), de quem (-ның), objeto (-ны), com (-мен).",
    "V": "Quase. Monte o verbo em peças: radical + tempo (ou negação) + pessoa.",
    "S": "Quase. Em cazaque o verbo vai no fim, e o que descreve vem antes do que é descrito.",
    "L": "Releia o vocabulário da aula: a palavra está lá.",
    "U": "Pense na situação: é formal (сіз) ou informal (сен)?",
    "R": "Volte ao texto e procure a frase que responde.",
}
LEVEL_TITLES = ["Жолаушы", "Шәкірт", "Аңшы", "Жігіт", "Шебер", "Ақын", "Шешен", "Би", "Дана", "Батыр"]
LEVEL_PT = ["Viajante", "Aprendiz", "Caçador", "Jovem valente", "Mestre artesão", "Poeta", "Orador", "Juiz da estepe", "Sábio", "Herói"]

# Letras cazaques e a letra russa com que costumam ser trocadas.
KZ_FOLD = str.maketrans({"ә": "а", "ө": "о", "ү": "у", "ұ": "у", "і": "и", "қ": "к", "ғ": "г", "ң": "н", "һ": "х"})
KZ_LETTERS = "әөүұіқғңһ"

TYPE_ORDER = {"mc": 0, "listen": 1, "pairs": 2, "order": 3, "gap": 4, "type": 5, "transform": 6, "dict": 7}
VOICES = {"A": "f", "B": "m"}
CYRILLIC = re.compile("[Ѐ-ӿ]")


def fold(text: str) -> str:
    return norm(text).translate(KZ_FOLD).replace("ё", "е")


def level_info(xp: int) -> dict:
    level, need = 0, 0
    while xp >= need + 300 * (level + 1):
        need += 300 * (level + 1)
        level += 1
    i = min(level, len(LEVEL_TITLES) - 1)
    return {"level": level + 1, "title": LEVEL_TITLES[i], "title_pt": LEVEL_PT[i], "into": xp - need, "span": 300 * (level + 1)}


def narration(lesson: dict) -> str:
    """Texto da narração em português (o TTS lê o português e, no meio, as palavras em cazaque)."""
    parts = [f"Aula {lesson['n']}. {lesson['title']}.", lesson.get("goal", "")]
    for rule in lesson.get("rules", []):
        parts.append(rule["title"] + ".")
        parts.extend(rule.get("points", []))
        if rule.get("trap"):
            parts.append("Atenção: " + rule["trap"])
    for sound in lesson.get("sounds", []):
        parts.append(f"Letra {sound['l'].split()[0]}: {sound['pt']}.")
    return " ".join(p.strip() for p in parts if p and p.strip())


class KazakhContent:
    def __init__(self, root: Path):
        self.root = root
        self.lessons: dict[str, dict] = {}
        self.order: list[str] = []
        self.items: dict[str, dict] = {}
        self.words: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        lessons = []
        for path in sorted((self.root / "lessons").glob("*.json")):
            lessons.extend(json.loads(path.read_text(encoding="utf-8"))["lessons"])
        lessons.sort(key=lambda l: l["n"])
        for lesson in lessons:
            lid = lesson["id"]
            lesson["item_ids"] = []
            for item in lesson.get("items", []):
                self.items[item["id"]] = {**item, "lesson": lid}
                lesson["item_ids"].append(item["id"])
            lesson["word_ids"] = []
            for i, entry in enumerate(lesson.get("vocab", []), 1):
                wid = f"{lid}-w{i:02d}"
                self.words[wid] = {"id": wid, "kz": entry[0], "pt": entry[1], "note": entry[2] if len(entry) > 2 else "", "lesson": lid}
                lesson["word_ids"].append(wid)
            self.lessons[lid] = lesson
            self.order.append(lid)

    def exists(self, item_id: str) -> bool:
        return item_id in self.items or item_id in self.words

    def label(self, item_id: str) -> str:
        if item_id in self.words:
            w = self.words[item_id]
            return f"{w['kz']} — {w['pt']}"
        item = self.items.get(item_id, {})
        answer = item.get("a") if isinstance(item.get("a"), str) else ""
        return item.get("q") or item.get("audio") or answer or item_id


class KazakhCourse:
    MAX_TRIES = {"mc": 2, "listen": 2, "fr_pt": 2, "pt_fr": 2, "gap": 3, "type": 3, "transform": 3, "order": 3, "dict": 2, "pairs": 1}

    def __init__(self, root: Path, db_path: Path):
        self.content = KazakhContent(root)
        self.progress = FrenchProgress(db_path, prefix="kz")
        self.pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _token(self, payload: dict) -> str:
        token = secrets.token_urlsafe(9)
        with self._lock:
            if len(self.pending) > 20000:
                self.pending.clear()
            self.pending[token] = {**payload, "tries": 0, "picks": 0}
        return token

    # -- progresso por aula
    def _lesson_state(self, lesson: dict, states: dict) -> dict:
        now = iso()
        ids = lesson["item_ids"]
        seen = sum(1 for i in ids if i in states)
        mastered = sum(1 for i in ids + lesson["word_ids"] if i in states and states[i]["stage"] >= MASTERED_STAGE)
        due = sum(1 for i in ids + lesson["word_ids"] if i in states and states[i]["due_at"] and states[i]["due_at"] <= now)
        return {"total": len(ids), "seen": seen, "done": bool(ids) and seen == len(ids), "mastered": mastered,
                "words": len(lesson["word_ids"]), "due": due}

    def free_mode(self) -> bool:
        return bool(self.progress.meta("free_mode", False))

    def unlocked(self, lesson_id: str, states: dict | None = None) -> bool:
        if self.free_mode():
            return True
        index = self.content.order.index(lesson_id)
        if index == 0:
            return True
        states = self.progress.states() if states is None else states
        prev = self.content.lessons[self.content.order[index - 1]]
        stars = self.progress.meta("lesson_stars", {})
        return self._lesson_state(prev, states)["done"] or stars.get(prev["id"], 0) > 0

    def overview(self) -> dict:
        states = self.progress.states()
        stars = self.progress.meta("lesson_stars", {})
        free = self.free_mode()
        modules: list[dict] = []
        previous_done = True
        next_id = ""
        for lid in self.content.order:
            lesson = self.content.lessons[lid]
            st = self._lesson_state(lesson, states)
            open_ = free or previous_done
            row = {"id": lid, "n": lesson["n"], "title": lesson["title"], "kz": lesson.get("kz", ""), "level": lesson["level"],
                   "goal": lesson.get("goal", ""), "stars": stars.get(lid, 0), "unlocked": open_, **st}
            if open_ and not st["done"] and not next_id:
                next_id = lid
            previous_done = st["done"] or stars.get(lid, 0) > 0
            if not modules or modules[-1]["title"] != lesson["module"]:
                modules.append({"title": lesson["module"], "level": lesson["level"], "lessons": []})
            modules[-1]["lessons"].append(row)
        profile = self.progress.profile()
        profile.update(level_info(int(profile["xp_total"])))
        done = sum(1 for m in modules for l in m["lessons"] if l["done"])
        return {"modules": modules, "profile": profile, "free_mode": free, "next": next_id, "done": done,
                "total": len(self.content.order), "categories": CATEGORIES,
                "achievements": self.achievements(profile, modules, stars)}

    def achievements(self, profile: dict, modules: list[dict], stars: dict) -> list[dict]:
        lessons = [l for m in modules for l in m["lessons"]]
        by_n = {l["n"]: l for l in lessons}
        done = lambda upto: all(by_n[n]["done"] for n in range(1, upto + 1) if n in by_n)  # noqa: E731
        three = sum(1 for v in stars.values() if v >= 3)
        defs = [
            ("alippe", "Әліппе", "Concluir as 6 aulas de sons e letras.", done(6)),
            ("a1", "Алғашқы қадам", "Concluir o A1 (aulas 1 a 20).", done(20)),
            ("a2", "Орта деңгей", "Concluir o A2 (aulas 1 a 32).", done(32)),
            ("b1", "Тәуелсіз", "Concluir todas as 40 aulas.", done(40)),
            ("star", "Үш жұлдыз", "Três estrelas no desafio de uma aula.", three >= 1),
            ("stars10", "Шоқжұлдыз", "Três estrelas em dez aulas.", three >= 10),
            ("recover", "Қайта оралу", "Recuperar 25 itens que você tinha errado.", profile["recovered"] >= 25),
            ("week", "Бір апта", "Sete dias seguidos cumprindo ao menos 1/3 da meta.", profile["streak"] >= 7),
            ("month", "Бір ай", "Trinta dias seguidos.", profile["streak"] >= 30),
            ("hundred", "Жүз", "Dominar 100 itens.", profile["mastered"] >= 100),
            ("words", "Сөздік", "Dominar 300 itens.", profile["mastered"] >= 300),
        ]
        return [{"id": i, "title": t, "desc": d, "done": bool(ok)} for i, t, d, ok in defs]

    # -- telas
    def lesson_screen(self, lesson: dict) -> dict:
        return {"type": "lesson", "lesson_id": lesson["id"], "n": lesson["n"], "title": lesson["title"], "kz": lesson.get("kz", ""),
                "level": lesson["level"], "module": lesson["module"], "goal": lesson.get("goal", ""), "rules": lesson.get("rules", []),
                "sounds": lesson.get("sounds", []), "narration": narration(lesson)}

    def vocab_screen(self, lesson: dict) -> dict:
        return {"type": "vocab", "lesson_id": lesson["id"], "n": lesson["n"],
                "words": [self.content.words[w] for w in lesson["word_ids"]]}

    def dialog_screen(self, lesson: dict) -> dict:
        dialog = lesson.get("dialog") or {}
        lines = [{"who": who, "kz": kz, "pt": pt, "voice": VOICES.get(who, "f")} for who, kz, pt in dialog.get("lines", [])]
        return {"type": "dialog", "lesson_id": lesson["id"], "title": dialog.get("title", ""), "lines": lines}

    def reading_screen(self, lesson: dict) -> dict | None:
        reading = lesson.get("reading")
        if not reading:
            return None
        return {"type": "reading", "lesson_id": lesson["id"], "title": reading["title"],
                "paragraphs": [{"kz": kz, "pt": pt} for kz, pt in reading["paragraphs"]]}

    def item_exercise(self, item_id: str) -> dict:
        item = self.content.items[item_id]
        lesson = self.content.lessons[item["lesson"]]
        t = item["t"]
        cat = item.get("c", "L")
        base = {"item_id": item_id, "kind": "u", "t": t, "category": cat, "category_label": CATEGORIES.get(cat, ""),
                "unit_id": lesson["id"], "unit_title": f"Aula {lesson['n']} · {lesson['title']}", "q": item.get("q", ""), "p": item.get("p", "")}
        pend = {"item_id": item_id, "kind": "u", "ref": lesson["id"], "category": cat, "t": t, "e": item.get("e", ""),
                "h": item.get("h", ""), "prompt": item.get("q", "") or item.get("p", "") or item.get("audio", "")}
        if t in ("mc", "listen"):
            base.update(options=shuffled([item["a"]] + list(item["w"])))
            if t == "listen":
                base.update(audio=item["audio"], q="", instruction=item.get("q") or "Ouça e escolha.")
            pend.update(accept=[item["a"]], answer=item["a"])
        elif t in ("gap", "type", "transform"):
            accept = item["a"] if isinstance(item["a"], list) else [item["a"]]
            if t == "type":
                base.update(instruction="Escreva em cazaque.")
            pend.update(accept=accept, answer=accept[0], typed=True)
            if t == "gap":
                full = re.sub(r"\s+([!?.,])", r"\1", item["q"].split("(")[0].replace("___", accept[0])).strip()
                base.update(blanks=item["q"].count("___"))
                pend.update(full=full)
        elif t == "order":
            words = item["a"].split()
            tokens = words + list(item.get("x", []))
            mixed = shuffled(tokens)
            while len(mixed) > 2 and mixed[:len(words)] == words:
                mixed = shuffled(tokens)
            base.update(tokens=mixed)
            pend.update(accept=[item["a"]], answer=item["a"], first=words[0])
        elif t == "pairs":
            pairs = item["p"]
            base.update(left=shuffled([p[0] for p in pairs]), right=shuffled([p[1] for p in pairs]))
            pend.update(pairs=[list(p) for p in pairs], answer="; ".join(f"{a} → {b}" for a, b in pairs))
        elif t == "dict":
            base.update(audio=item["a"])
            pend.update(answer=item["a"], accept=[item["a"]], typed=True, dictation=True)
        else:
            raise ValueError(f"Tipo desconhecido: {t}")
        pend["speak"] = self._speak(item)
        base["max_tries"] = self.MAX_TRIES.get(t, 2)
        base["token"] = self._token(pend)
        return base

    @staticmethod
    def _speak(item: dict) -> str:
        """O que tocar depois da resposta: só texto em cazaque (nunca a tradução em português)."""
        t, answer = item["t"], item.get("a")
        first = answer[0] if isinstance(answer, list) else answer
        if t == "listen":
            return item["audio"]
        if t in ("order", "dict", "transform", "type"):
            return first
        if t in ("mc", "gap") and isinstance(first, str):
            q = item.get("q", "").split("(")[0]
            if "___" in q and CYRILLIC.search(q) and CYRILLIC.search(first) and "→" not in q and "+" not in q:
                return q.replace("___", first).strip()
            return first if CYRILLIC.search(first) and not re.search(r"[A-Za-z]", first) else ""
        return ""

    def word_exercise(self, word_id: str, variant: str) -> dict:
        word = self.content.words[word_id]
        lesson = self.content.lessons[word["lesson"]]
        pool = [self.content.words[w] for w in lesson["word_ids"] if w != word_id]
        if len(pool) < 3:  # aulas com pouco vocabulário pegam distratores da aula anterior
            index = self.content.order.index(lesson["id"])
            for lid in self.content.order[max(0, index - 2):index]:
                pool += [self.content.words[w] for w in self.content.lessons[lid]["word_ids"]]
        base = {"item_id": word_id, "kind": "w", "theme_name": f"Aula {lesson['n']}", "unit_title": f"Aula {lesson['n']}",
                "category": "L", "category_label": CATEGORIES["L"]}
        pend = {"item_id": word_id, "kind": "w", "ref": lesson["id"], "category": "L", "e": word.get("note", ""),
                "prompt": word["kz"]}
        if variant == "pt_kz":
            others = [w["kz"] for w in pool if norm(w["kz"]) != norm(word["kz"])]
            options = shuffled([word["kz"]] + random.sample(others, min(3, len(others))))
            base.update(t="pt_fr", q=word["pt"], options=options, instruction="Como se diz em cazaque?", audio_after=word["kz"])
            pend.update(t="pt_fr", accept=[word["kz"]], answer=word["kz"])
        else:
            others = [w["pt"] for w in pool if norm(w["pt"]) != norm(word["pt"])]
            options = shuffled([word["pt"]] + random.sample(others, min(3, len(others))))
            if variant == "listen":
                base.update(t="listen", q="", audio=word["kz"], options=options, instruction="Ouça e escolha o significado.")
                pend.update(t="listen")
            else:
                base.update(t="fr_pt", q=word["kz"], audio=word["kz"], options=options, instruction="O que significa?")
                pend.update(t="fr_pt")
            pend.update(accept=[word["pt"]], answer=word["pt"])
        pend["speak"] = word["kz"]
        base["max_tries"] = 2
        base["token"] = self._token(pend)
        return base

    def _word_steps(self, word_ids: list[str], count: int, states: dict) -> list[dict]:
        ranked = sorted(word_ids, key=lambda w: (states[w]["stage"] if w in states else -1, random.random()))
        variants = ["fr_pt", "listen", "pt_kz"]
        steps = []
        for i, wid in enumerate(ranked[:count]):
            steps.append(self.word_exercise(wid, variants[i % len(variants)]))
        return steps

    # -- sessões
    def lesson_session(self, lesson_id: str, mode: str) -> dict:
        lesson = self.content.lessons.get(lesson_id)
        if not lesson:
            raise ValueError("Aula desconhecida.")
        states = self.progress.states()
        if not self.unlocked(lesson_id, states):
            raise ValueError("Esta aula ainda está trancada. Conclua a aula anterior (ou ligue o modo livre).")
        title = f"Aula {lesson['n']} · {lesson['title']}"
        if mode == "challenge":
            steps = [self.item_exercise(i) for i in shuffled(lesson["item_ids"])]
            steps += self._word_steps(lesson["word_ids"], 4, states)
            return {"mode": "challenge", "title": f"Desafio · {title}", "unit_id": lesson_id, "steps": steps}
        if mode == "vocab":
            steps = [self.vocab_screen(lesson)] + self._word_steps(lesson["word_ids"], len(lesson["word_ids"]), states)
            return {"mode": "vocab", "title": f"Vocabulário · {title}", "unit_id": lesson_id, "steps": steps}
        steps: list[dict] = [self.lesson_screen(lesson), self.vocab_screen(lesson)]
        steps += self._word_steps(lesson["word_ids"], 6, states)
        if lesson.get("dialog"):
            steps.append(self.dialog_screen(lesson))
        reading = self.reading_screen(lesson)
        if reading:
            steps.append(reading)
        steps += [self.item_exercise(i) for i in lesson["item_ids"]]
        return {"mode": "learn", "title": title, "unit_id": lesson_id, "steps": steps}

    def review_session(self, size: int = 20) -> dict:
        now = iso()
        states = self.progress.states()
        due = sorted((s for s in states.values() if s["due_at"] and s["due_at"] <= now and self.content.exists(s["item_id"])),
                     key=lambda s: (s["stage"], s["due_at"]))[:size]
        steps = []
        for state in due:
            item_id = state["item_id"]
            if item_id in self.content.words:
                steps.append(self.word_exercise(item_id, random.choice(["fr_pt", "listen", "pt_kz"])))
            else:
                steps.append(self.item_exercise(item_id))
        return {"mode": "review", "title": "Revisão do dia", "steps": steps}

    def again(self, item_id: str) -> dict:
        if item_id in self.content.words:
            return self.word_exercise(item_id, random.choice(["fr_pt", "listen", "pt_kz"]))
        if item_id in self.content.items:
            return self.item_exercise(item_id)
        raise ValueError("Item desconhecido.")

    def lesson_detail(self, lesson_id: str) -> dict:
        lesson = self.content.lessons.get(lesson_id)
        if not lesson:
            raise ValueError("Aula desconhecida.")
        states = self.progress.states()
        words = [{**self.content.words[w], "stage": states[w]["stage"] if w in states else None} for w in lesson["word_ids"]]
        return {**self.lesson_screen(lesson), "words": words, "dialog": self.dialog_screen(lesson) if lesson.get("dialog") else None,
                "reading": self.reading_screen(lesson), "unlocked": self.unlocked(lesson_id, states),
                "stars": self.progress.meta("lesson_stars", {}).get(lesson_id, 0), **self._lesson_state(lesson, states)}

    def mark_seen(self, item_ids: list[str]) -> dict:
        gained = 0
        for item_id in item_ids[:40]:
            if item_id not in self.content.words:
                continue
            if self.progress.mark_seen(item_id, "w", self.content.words[item_id]["lesson"]):
                gained += XP_INTRO
        xp = self.progress.add_xp(gained)
        return {"ok": True, "xp": gained, "xp_today": xp}

    def finish(self, payload: dict) -> dict:
        result: dict = {}
        lesson_id = str(payload.get("unit_id", ""))
        if payload.get("mode") == "challenge" and lesson_id in self.content.lessons:
            rate = self.progress.challenge_rate(self.content.lessons[lesson_id]["item_ids"])
            got = 3 if rate >= 0.95 else 2 if rate >= 0.8 else 1 if rate >= 0.6 else 0
            stars = self.progress.meta("lesson_stars", {})
            result.update(stars=got, best_stars=max(got, stars.get(lesson_id, 0)), new_best=got > stars.get(lesson_id, 0))
            if got > stars.get(lesson_id, 0):
                stars[lesson_id] = got
                self.progress.set_meta("lesson_stars", stars)
        if lesson_id in self.content.lessons:
            lesson = self.content.lessons[lesson_id]
            result["lesson_done"] = self._lesson_state(lesson, self.progress.states())["done"]
            index = self.content.order.index(lesson_id)
            if index + 1 < len(self.content.order):
                nxt = self.content.lessons[self.content.order[index + 1]]
                result["next"] = {"id": nxt["id"], "n": nxt["n"], "title": nxt["title"], "unlocked": self.unlocked(nxt["id"])}
        profile = self.progress.profile()
        profile.update(level_info(int(profile["xp_total"])))
        result["profile"] = profile
        return result

    def set_goal(self, goal: int) -> dict:
        if goal not in (50, 100, 150, 250, 400):
            raise ValueError("Meta inválida.")
        self.progress.set_meta("daily_goal", goal)
        return self.overview()["profile"]

    def set_free_mode(self, on: bool) -> dict:
        self.progress.set_meta("free_mode", bool(on))
        return {"free_mode": bool(on)}

    # -- correção
    def answer(self, payload: dict) -> dict:
        token = str(payload.get("token", ""))
        with self._lock:
            pend = self.pending.get(token)
        if not pend:
            raise ValueError("Esta pergunta expirou. Feche a sessão e comece outra.")
        mode = str(payload.get("mode", ""))
        given = payload.get("answer", "")
        if not isinstance(given, list) and not norm(given) and "pairs" not in pend:
            return {"final": False, "correct": False, "try": pend["tries"], "hint": "Escreva uma resposta (vale tentar).", "verdict": "empty"}
        pend["tries"] += 1
        tries = pend["tries"]
        max_tries = self.MAX_TRIES.get(pend.get("t", ""), 2)
        extra: dict = {}
        if "pairs" in pend:
            score, marks = grade_pairs(pend["pairs"], given if isinstance(given, list) else [])
            extra["marks"] = marks
            given_text = "; ".join(f"{p.get('left')} → {p.get('right')}" for p in given if isinstance(p, dict)) if isinstance(given, list) else ""
            return self._finalize(token, pend, score, given_text, mode, extra, score >= 1)
        given_text = str(given)
        verdict = self._check(pend, given_text)
        if pend.get("dictation"):
            ratio, words = dictation_marks(given_text, pend["answer"])
            extra["words"] = words
            if verdict == "wrong" and ratio >= 0.999:
                verdict = "close"
        if verdict == "ok":
            return self._finalize(token, pend, SCORE_BY_TRY.get(tries, 0.4), given_text, mode, extra, True)
        if tries < max_tries:
            return {"final": False, "correct": False, "try": tries, "hint": self._hint(pend, tries, verdict), "verdict": verdict, **extra}
        return self._finalize(token, pend, 0.0, given_text, mode, extra, False)

    def _check(self, pend: dict, given: str) -> str:
        answer = norm(given)
        if not answer:
            return "empty"
        accept = [norm(a) for a in pend.get("accept", []) if a]
        if answer in accept:
            return "ok"
        if not pend.get("typed") and pend.get("t") != "order":
            return "wrong"
        folded = fold(given)
        if any(folded == fold(a) for a in accept):
            return "letters"
        best = max((difflib.SequenceMatcher(None, answer, a).ratio() for a in accept), default=0)
        return "close" if best >= 0.85 else "wrong"

    def _hint(self, pend: dict, tries: int, verdict: str) -> str:
        if verdict == "letters":
            return "Quase! As letras certas, mas faltou usar uma letra cazaque (ә ө ү ұ і қ ғ ң): confira k/қ, у/ү/ұ, и/і…"
        if pend.get("t") == "order":
            return "A ordem ainda não está certa (o verbo vai no fim)." if tries == 1 else f"Dica: a frase começa por «{pend.get('first', '')}»."
        if tries == 1:
            signal = SIGNALS.get(pend.get("category", ""), "Quase. Releia com calma.")
            return ("Está muito perto: confira letra por letra. " + signal.replace("Quase. ", "")) if verdict == "close" else signal
        return pend.get("h") or first_sentence(pend.get("e", "")) or "Volte à explicação da aula."

    def _finalize(self, token: str, pend: dict, score: float, given: str, mode: str, extra: dict, correct: bool) -> dict:
        with self._lock:
            self.pending.pop(token, None)
        state = self.progress.record(pend["item_id"], pend["kind"], pend.get("ref", ""), pend.get("category", ""), mode, score,
                                     pend["tries"], given, str(pend.get("answer", "")), str(pend.get("prompt", "")))
        xp = XP_BY_TRY[1] if score >= 1 else XP_BY_TRY[2] if score >= 0.7 else XP_BY_TRY[3] if score > 0 else XP_FAIL
        bonus = XP_RECOVERY if state["recovered"] else 0
        xp_today = self.progress.add_xp(xp + bonus)
        return {"final": True, "correct": correct, "score": score, "try": pend["tries"], "answer": pend.get("answer", ""),
                "explanation": pend.get("e", ""), "full": pend.get("full", ""), "translation": "", "xp": xp, "bonus": bonus,
                "recovered": state["recovered"], "xp_today": xp_today, "state": state, "speak": pend.get("speak", ""), **extra}


def all_audio_texts(content: KazakhContent) -> list[tuple[str, str, str]]:
    """(texto, voz, modo) de todo áudio do curso, para gerar antes (tools/pregenerate_kazakh_audio.py)."""
    out: list[tuple[str, str, str]] = []
    for lid in content.order:
        lesson = content.lessons[lid]
        out.append((narration(lesson), "", "lesson"))
        for rule in lesson.get("rules", []):
            out += [(ex[0], "f", "kk") for ex in rule.get("ex", [])]
        for sound in lesson.get("sounds", []):
            out += [(w[0], "f", "kk") for w in sound.get("words", [])]
        out += [(content.words[w]["kz"], "f", "kk") for w in lesson["word_ids"]]
        for who, kz, _ in (lesson.get("dialog") or {}).get("lines", []):
            out.append((kz, VOICES.get(who, "f"), "kk"))
        for kz, _ in (lesson.get("reading") or {}).get("paragraphs", []):
            out.append((kz, "f", "kk"))
        for item_id in lesson["item_ids"]:
            item = content.items[item_id]
            if item["t"] == "listen":
                out.append((item["audio"], "f", "kk"))
            elif item["t"] in ("dict", "order"):
                out.append((item["a"], "f", "kk"))
            elif item["t"] in ("mc", "pt_fr") and any(c in KZ_LETTERS for c in item["a"].lower()):
                out.append((item["a"], "f", "kk"))
    seen, unique = set(), []
    for entry in out:
        if entry[0] and entry not in seen:
            seen.add(entry)
            unique.append(entry)
    return unique
