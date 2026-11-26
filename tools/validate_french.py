#!/usr/bin/env python3
"""Valida o conteúdo do curso de francês (data/fr): formato, gabaritos e conjugação.

Formato de uma unidade (data/fr/units/*.json → {"units": [...]}):
    {"id": "u01", "n": 1, "phase": 1, "prio": 1-3, "theme": "<eixo>", "title", "goal", "extra": false,
     "rules": [{"title", "points": [...], "ex": [["fr", "pt"]], "trap": "..."}],
     "items": [ITEM]}

ITEM (t = tipo; c = categoria do caderno de erros; e = explicação obrigatória; h = pista opcional):
    mc        {"q": "frase com ___", "a": "certa", "w": [3 erradas]}
    gap       {"q": "frase com um ___", "a": ["aceitas"], "p": "tradução"}
    fix       {"q": "frase com erro", "bad": "trecho errado (palavras inteiras)", "a": ["correção do trecho"], "full": "frase certa"}
    order     {"a": "frase sem ponto final", "x": ["palavra intrusa"]}
    transform {"p": "instrução", "q": "frase de partida", "a": ["aceitas"], "start": "início sugerido"}
    pairs     {"p": [["esquerda", "direita"], ...]}  (3 a 6 pares, sem repetição)
    register  {"q": "frase", "a": "familiar|neutro|formal"}
    dict      {"a": "frase para ditado"}

Eixo (data/fr/themes/*.json → {"themes": [...]}):
    {"id", "n", "name", "fr", "color", "desc", "delf": bool, "units": [n...],
     "words": [{"fr": "le loyer", "pt": "o aluguel", "lv": "B1|B2|C1", "ex": "frase", "ex_pt": "...", "n": "nota", "g": "m|f", "reg": "fam."}]}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from french import CATEGORIES, TENSES, FrenchContent, accepted_forms, conjugate, norm, strip_punct  # noqa: E402

FR = BASE / "data" / "fr"
TYPES = {"mc", "gap", "fix", "order", "transform", "pairs", "register", "dict"}
LEVELS = {"B1", "B2", "C1"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    errors: list[str] = []
    warnings: list[str] = []
    try:
        content = FrenchContent(FR)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO ao carregar o conteúdo: {exc}")
        return 1
    ids: set[str] = set()
    numbers: dict[tuple, str] = {}
    theme_ids = set(content.themes)
    for unit_id in content.unit_order:
        unit = content.units[unit_id]
        where = f"unidade {unit_id}"
        for key in ("n", "phase", "title", "goal", "rules", "items"):
            if key not in unit:
                errors.append(f"{where}: falta {key}")
        if unit.get("theme") and unit["theme"] not in theme_ids:
            warnings.append(f"{where}: eixo «{unit['theme']}» não existe")
        number_key = (unit.get("phase"), unit.get("n"))
        if number_key in numbers:
            errors.append(f"{where}: número repetido com {numbers[number_key]}")
        numbers[number_key] = unit_id
        if len(unit.get("items", [])) < 8:
            warnings.append(f"{where}: só {len(unit.get('items', []))} exercícios")
        for rule in unit.get("rules", []):
            if not rule.get("title") or not rule.get("points"):
                errors.append(f"{where}: regra sem título ou pontos")
        for item in unit.get("items", []):
            iw = f"{where} / {item.get('id')}"
            if item.get("id") in ids:
                errors.append(f"{iw}: id repetido")
            ids.add(item.get("id"))
            t = item.get("t")
            if t not in TYPES:
                errors.append(f"{iw}: tipo desconhecido {t}")
                continue
            if item.get("c") not in CATEGORIES:
                errors.append(f"{iw}: categoria inválida {item.get('c')}")
            if not item.get("e"):
                errors.append(f"{iw}: falta a explicação (e)")
            try:
                check_item(item, iw, errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{iw}: {exc}")
    for theme_id in content.theme_order:
        theme = content.themes[theme_id]
        where = f"eixo {theme_id}"
        seen: set[str] = set()
        if len(theme.get("words", [])) < 12:
            warnings.append(f"{where}: só {len(theme.get('words', []))} palavras")
        for word in theme.get("words", []):
            key = norm(word.get("fr", ""))
            if key in seen:
                errors.append(f"{where}: palavra repetida «{word.get('fr')}»")
            seen.add(key)
            if not word.get("pt"):
                errors.append(f"{where}: «{word.get('fr')}» sem tradução")
            if word.get("lv") not in LEVELS:
                errors.append(f"{where}: «{word.get('fr')}» com nível inválido {word.get('lv')}")
            if word.get("fr", "").startswith(("l'", "les ")) and not word.get("g") and not word.get("pos"):
                warnings.append(f"{where}: «{word['fr']}» sem gênero (g)")
            if word.get("ex") and not word.get("ex_pt"):
                warnings.append(f"{where}: «{word['fr']}» com exemplo sem tradução")
    for inf, verb in content.verbs.items():
        try:
            table = conjugate(verb)
            for tense in TENSES:
                if tense == "impe" and (verb.get("no_impe") or verb.get("impersonal")):
                    continue
                persons = [2] if verb.get("impersonal") else ([0, 1, 2] if tense == "impe" else range(6))
                for person in persons:
                    form = table[tense][person]
                    if not form or "-" == form.strip():
                        errors.append(f"verbo {inf}: forma vazia em {tense}/{person}")
                    if tense != "impe":
                        accepted_forms(verb, tense, person, ["je", "tu", "il", "nous", "vous", "ils"][person])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"verbo {inf}: {exc}")
    total_items = len(content.items)
    total_words = len(content.words)
    print(f"{len(content.units)} unidades, {total_items} exercícios, {len(content.themes)} eixos, {total_words} palavras, {len(content.verbs)} verbos.")
    for warning in warnings:
        print("aviso:", warning)
    for error in errors:
        print("ERRO:", error)
    return 1 if errors else 0


def check_item(item: dict, where: str, errors: list[str]) -> None:
    t = item["t"]
    if t == "mc":
        wrong = item.get("w", [])
        if len(wrong) != 3:
            errors.append(f"{where}: mc precisa de 3 alternativas erradas")
        if norm(item["a"]) in {norm(w) for w in wrong}:
            errors.append(f"{where}: a resposta aparece entre as erradas")
        if len({norm(w) for w in wrong}) != len(wrong):
            errors.append(f"{where}: alternativas repetidas")
        q = item.get("q", "").rstrip()
        if "___" not in q and not q.endswith(("?", ":", "=", "…")):
            errors.append(f"{where}: mc sem lacuna ___ nem pergunta (termine com ? : = …)")
    elif t == "gap":
        if item.get("q", "").count("___") != 1:
            errors.append(f"{where}: gap precisa de exatamente uma lacuna ___")
        if not isinstance(item.get("a"), list) or not item["a"]:
            errors.append(f"{where}: gap precisa de lista de respostas")
    elif t == "fix":
        tokens = item["q"].split()
        bad = item["bad"].split()
        found = any([strip_punct(x) for x in tokens[i:i + len(bad)]] == [strip_punct(b) for b in bad] for i in range(len(tokens)))
        if not found:
            errors.append(f"{where}: o trecho errado «{item['bad']}» não está na frase (palavras inteiras)")
        if not item.get("a") or not item.get("full"):
            errors.append(f"{where}: fix precisa de a (correção) e full (frase certa)")
        if any(norm(a) == norm(item["bad"]) for a in item["a"]):
            errors.append(f"{where}: a correção é igual ao erro")
    elif t == "order":
        words = item["a"].split()
        if len(words) < 3:
            errors.append(f"{where}: frase curta demais para montar")
        if re.search(r"[.!]$", item["a"]):
            errors.append(f"{where}: tire o ponto final da frase de montagem")
        if any(norm(x) in {norm(w) for w in words} for x in item.get("x", [])):
            errors.append(f"{where}: a palavra intrusa também está na frase")
    elif t == "transform":
        if not item.get("p") or not item.get("q") or not item.get("a"):
            errors.append(f"{where}: transform precisa de p, q e a")
    elif t == "pairs":
        pairs = item.get("p", [])
        if not 3 <= len(pairs) <= 6:
            errors.append(f"{where}: pairs precisa de 3 a 6 pares")
        if len({norm(a) for a, _ in pairs}) != len(pairs) or len({norm(b) for _, b in pairs}) != len(pairs):
            errors.append(f"{where}: pares com lados repetidos")
    elif t == "register":
        if item.get("a") not in ("familiar", "neutro", "formal"):
            errors.append(f"{where}: register precisa de a = familiar|neutro|formal")
    elif t == "dict":
        if len(item.get("a", "")) > 160:
            errors.append(f"{where}: ditado longo demais")


if __name__ == "__main__":
    sys.exit(main())
