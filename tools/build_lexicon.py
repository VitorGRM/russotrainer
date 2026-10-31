#!/usr/bin/env python3
"""Constrói data/lexicon.sqlite3.gz: todo o OpenRussian, priorizado, traduzido e classificado por tema.

Fontes (baixadas na primeira execução para --cache):
  - OpenRussian / Badestrand russian-dictionary (CC BY-SA 4.0): lemas, acento, formas, aspecto, gênero.
  - FrequencyWords de Hermit Dave (CC BY-SA 4.0, legendas OpenSubtitles 2018): frequência de formas.
  - Tabelas de tradução do Wiktionary inglês, extraídas por Matthias Buchmeier e publicadas pelo
    Open DSL Dictionary Project (CC BY-SA 3.0): ligam russo e português pela mesma acepção inglesa.
  - Princeton WordNet 3.0 + OpenWN-PT (CC BY-SA), via pacotes de dados do NLTK: hierarquia
    semântica para os temas e reserva de traduções em português.
Curadoria própria (no repositório):
  - data/themes.json: os eixos temáticos e as regras de classificação;
  - data/curation/pt_overrides.tsv: traduções portuguesas revistas (têm prioridade);
  - data/curation/theme_overrides.tsv: ajustes manuais de tema.

Uso (precisa de internet e do pacote nltk só para construir; o app não depende deles):
    python tools/build_lexicon.py --cache .cache/lexicon
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OUTPUT = DATA / "lexicon.sqlite3.gz"
OR_RAW = "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master"
SOURCES = {
    "nouns.csv": f"{OR_RAW}/nouns.csv",
    "adjectives.csv": f"{OR_RAW}/adjectives.csv",
    "verbs.csv": f"{OR_RAW}/verbs.csv",
    "others.csv": f"{OR_RAW}/others.csv",
    "ru_50k.txt": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ru/ru_50k.txt",
    "en-ru.txt": "https://raw.githubusercontent.com/open-dsl-dict/wiktionary-dict/master/src/en-ru-enwiktionary.txt",
    "en-pt.txt": "https://raw.githubusercontent.com/open-dsl-dict/wiktionary-dict/master/src/en-pt-enwiktionary.txt",
    "wordnet.zip": "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip",
    "omw-1.4.zip": "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/omw-1.4.zip",
}
POS_FILES = {"noun": "nouns.csv", "adjective": "adjectives.csv", "verb": "verbs.csv", "other": "others.csv"}
FORM_COLUMNS = {
    "noun": ["sg_nom", "sg_gen", "sg_dat", "sg_acc", "sg_inst", "sg_prep", "pl_nom", "pl_gen", "pl_dat", "pl_acc", "pl_inst", "pl_prep"],
    "adjective": ["comparative", "superlative", "short_m", "short_f", "short_n", "short_pl"]
    + [f"decl_{g}_{c}" for g in ("m", "f", "n", "pl") for c in ("nom", "gen", "dat", "acc", "inst", "prep")],
    "verb": ["imperative_sg", "imperative_pl", "past_m", "past_f", "past_n", "past_pl",
             "presfut_sg1", "presfut_sg2", "presfut_sg3", "presfut_pl1", "presfut_pl2", "presfut_pl3"],
    "other": [],
}
# Patamares de utilidade pelo posto na lista de frequência (aproximação do QECR para léxico).
LEVELS = [(1200, "A2"), (3500, "B1"), (8000, "B2"), (16000, "C1"), (10**9, "C2")]
WN_POS = {"noun": "n", "verb": "v", "adjective": "a", "other": None}


# ----------------------------------------------------------------------------- utilidades
def log(message: str) -> None:
    print(message, flush=True)


def fetch(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = cache / name
        if target.exists() and target.stat().st_size > 0:
            continue
        log(f"Baixando {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "LinguaLab-build/2.0"})
        with urllib.request.urlopen(request, timeout=300) as response, open(target.with_suffix(".part"), "wb") as out:
            shutil.copyfileobj(response, out)
        target.with_suffix(".part").replace(target)
    nltk_dir = cache / "nltk_data" / "corpora"
    for name in ("wordnet", "omw-1.4"):
        if not (nltk_dir / name).exists():
            nltk_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(cache / f"{name}.zip") as archive:
                archive.extractall(nltk_dir)
    os.chmod(cache / "nltk_data", 0o755)
    for root, dirs, files in os.walk(cache / "nltk_data"):
        for item in dirs + files:
            os.chmod(os.path.join(root, item), 0o755 if item in dirs else 0o644)


def plain(value: str) -> str:
    """Forma sem acento e com е no lugar de ё, para índices e comparação."""
    text = unicodedata.normalize("NFC", value or "").lower()
    text = text.replace("ё", "е").replace("'", "").replace("´", "").replace("\u0301", "")
    return text.strip()


def stress(value: str) -> str:
    """Converte o apóstrofo do OpenRussian (челове'к) em acento agudo combinado (челове́к)."""
    return re.sub(r"(\w)'", "\\1\u0301", value or "")


def split_top(text: str, seps: str = ",;") -> list[str]:
    """Divide por vírgula/ponto e vírgula fora de parênteses, colchetes e barras de transcrição."""
    parts, depth, slash, buf = [], 0, False, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == "/" and depth == 0:
            slash = not slash
        if ch in seps and depth == 0 and not slash:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def clean_translation(item: str) -> str:
    item = re.sub(r"\{[^}]*\}|\[[^\]]*\]|/[^/]*/|\([^)]*\)", " ", item)
    return re.sub(r"\s+", " ", item).strip(" .;:")


def gloss_terms(en: str, pos: str) -> list[str]:
    terms = []
    for raw in split_top(en or ""):
        term = re.sub(r"\([^)]*\)", " ", raw).strip()
        if pos == "verb":
            term = re.sub(r"^to\s+", "", term)
        term = re.sub(r"\s+", " ", term).strip(" .")
        if term and term not in terms:
            terms.append(term)
    return terms


# ----------------------------------------------------------------------------- leitura das fontes
def load_openrussian(cache: Path) -> list[dict]:
    entries: list[dict] = []
    for pos, filename in POS_FILES.items():
        with open(cache / filename, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_MINIMAL))
        for index, row in enumerate(rows):
            lemma = (row.get("bare") or "").strip()
            if not lemma or not re.search(r"[а-яё]", lemma.lower()):
                continue
            forms = {}
            for column in FORM_COLUMNS[pos]:
                value = (row.get(column) or "").strip()
                if value:
                    forms[column] = stress(value)
            entries.append({
                "lemma": lemma,
                "accented": stress((row.get("accented") or lemma).strip()),
                "pos": pos,
                "en": (row.get("translations_en") or "").strip(),
                "gender": (row.get("gender") or "").strip(),
                "animate": (row.get("animate") or "").strip() == "1",
                "indeclinable": (row.get("indeclinable") or "").strip() == "1",
                "sg_only": (row.get("sg_only") or "").strip() == "1",
                "pl_only": (row.get("pl_only") or "").strip() == "1",
                "aspect": (row.get("aspect") or "").strip(),
                "partner": (row.get("partner") or "").strip(),
                "forms": forms,
                "file_pos": index / max(1, len(rows)),
            })
    for number, entry in enumerate(entries, start=1):
        entry["id"] = number
    return entries


def load_frequencies(cache: Path) -> dict[str, int]:
    freq: dict[str, int] = collections.Counter()
    for line in open(cache / "ru_50k.txt", encoding="utf-8"):
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            freq[plain(parts[0])] += int(parts[1])
    return freq


WIKT_LINE = re.compile(r"^(.+?) \{([^}]*)\}( /[^/]*/)? \((.*?)\) :: (.*)$")
EUROPEAN_PT = re.compile(r"\[(?:PT|Portugal|European Portuguese|Portugal and Africa)\]")
PRIMARY_SENSES: set[tuple[str, str, str]] = set()


def load_wiktionary(path: Path) -> dict[tuple[str, str, str], list[str]]:
    """Lê 'head {pos} /ipa/ (acepção) :: tradução, tradução'. A linha com IPA é a primeira acepção do verbete."""
    table: dict[tuple[str, str, str], list[str]] = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or "SEE:" in line:
            continue
        match = WIKT_LINE.match(line.rstrip("\n"))
        if not match:
            continue
        head, pos, ipa, sense, translations = match.groups()
        key = (head, pos, sense)
        if ipa:
            PRIMARY_SENSES.add(key)
        items = split_top(translations, ",")
        brazil = [i for i in items if re.search(r"\[(?:BR|Brazil)\]", i)]
        for item in items:
            if EUROPEAN_PT.search(item) and brazil:
                continue
            text = clean_translation(item)
            if text and text not in table[key]:
                table[key].append(text)
    return table


# ----------------------------------------------------------------------------- frequência e nível
def compute_ranks(entries: list[dict], freq: dict[str, int]) -> None:
    owners: dict[str, list[int]] = collections.defaultdict(list)
    for entry in entries:
        seen = {plain(entry["lemma"])}
        for value in entry["forms"].values():
            for variant in split_top(value, ","):
                seen.add(plain(variant))
        for form in seen:
            if form:
                owners[form].append(entry["id"])
    lemma_of: dict[str, set[int]] = collections.defaultdict(set)
    for entry in entries:
        lemma_of[plain(entry["lemma"])].add(entry["id"])
    score = collections.Counter()
    for form, ids in owners.items():
        count = freq.get(form, 0)
        if not count:
            continue
        # Uma forma igual ao lema de alguém (ладно, есть, мой) pertence sobretudo a esse lema.
        heads = [i for i in ids if i in lemma_of.get(form, ())]
        others = [i for i in ids if i not in heads]
        if heads and others:
            for entry_id in heads:
                score[entry_id] += 0.85 * count / len(heads)
            for entry_id in others:
                score[entry_id] += 0.15 * count / len(others)
        else:
            for entry_id in ids:
                score[entry_id] += count / len(ids)
    for entry in entries:
        entry["freq"] = round(score.get(entry["id"], 0.0), 1)
    # Duas opiniões sobre utilidade: a fala (legendas) e o posto que o OpenRussian dá a cada palavra
    # dentro da sua classe, vindo de um corpus geral. A média geométrica dos postos evita que o
    # vocabulário de seriado (зомби, агент) passe à frente do vocabulário de jornal e de livro.
    by_speech = sorted(entries, key=lambda e: (-e["freq"], e["file_pos"]))
    speech_rank = {e["id"]: i for i, e in enumerate(by_speech, start=1)}
    total = len(entries)
    for entry in entries:
        general_rank = 1 + entry["file_pos"] * total
        entry["blend"] = math.exp(0.5 * math.log(speech_rank[entry["id"]]) + 0.5 * math.log(general_rank))
    ordered = sorted(entries, key=lambda e: (e["blend"], e["file_pos"]))
    for rank, entry in enumerate(ordered, start=1):
        entry["rank"] = rank
        entry["level"] = next(label for limit, label in LEVELS if rank <= limit)


# ----------------------------------------------------------------------------- português
MARGINAL = re.compile(r"slang|sarcas|vulgar|obsolete|archaic|dated|rare|figurative|colloquial|informal|derogatory|offensive|euphemis|humorous|nautical|dialect", re.I)
WIKT_POS = {"noun": {"n"}, "verb": {"v"}, "adjective": {"adj"}, "other": {"adv", "prep", "conj", "pron", "interj", "particle", "num", "phrase", "determiner", "article", "contraction"}}


def portuguese_candidates(entries, ru_table, pt_table, wn, por_lemmas, overrides) -> None:
    ru_to_keys: dict[str, list[tuple]] = collections.defaultdict(list)
    for key, words in ru_table.items():
        for word in words:
            ru_to_keys[plain(word)].append(key)
    pt_by_head: dict[tuple[str, str], list[list[str]]] = collections.defaultdict(list)
    for (head, pos, _sense), words in pt_table.items():
        pt_by_head[(head.lower(), pos)].append(words)

    stats = collections.Counter()
    for entry in entries:
        key = (plain(entry["lemma"]), entry["pos"])
        if key in overrides:
            entry["pt"] = overrides[key]
            entry["pt_source"] = "curadoria"
            stats["curadoria"] += 1
            continue
        terms = gloss_terms(entry["en"], entry["pos"])
        lowered = [t.lower() for t in terms]
        wikt_pos = WIKT_POS[entry["pos"]]
        found: list[str] = []
        source = ""
        # 1) Mesma acepção: a tabela de tradução que contém a palavra russa também traz o português.
        sense_hits = []
        lemma_plain = plain(entry["lemma"])
        for wkey in ru_to_keys.get(lemma_plain, []):
            head, pos, sense = wkey
            if pos not in wikt_pos or wkey not in pt_table:
                continue
            order = lowered.index(head.lower()) if head.lower() in lowered else 50
            marginal = 1 if MARGINAL.search(sense) else 0
            ru_words = [plain(w) for w in ru_table[wkey]]
            position = ru_words.index(lemma_plain) if lemma_plain in ru_words else 9
            sense_hits.append(((order, marginal, 0 if wkey in PRIMARY_SENSES else 1, position), wkey))
        sense_hits.sort(key=lambda item: item[0])
        for rank_key, wkey in sense_hits:
            order = rank_key[0]
            if order == 50 and terms and len(found) >= 1:
                continue
            if rank_key[1] and found:
                continue
            for word in pt_table[wkey][:2]:
                if word not in found:
                    found.append(word)
        if found:
            source = "wiktionary"
        # 2) Glosa inglesa do OpenRussian -> português pelo Wiktionary (primeira acepção do termo).
        if len(found) < 2:
            for term in lowered[:3]:
                for pos in wikt_pos:
                    for words in pt_by_head.get((term, pos), [])[:1]:
                        for word in words[:1]:
                            if word not in found:
                                found.append(word)
                                source = source or "wiktionary-en"
                if len(found) >= 3:
                    break
        # 3) WordNet em português (OpenWN-PT), primeiro sentido de cada termo.
        if not found and wn is not None:
            wpos = WN_POS[entry["pos"]]
            for term in terms[:3]:
                for synset in wn.synsets(term.replace(" ", "_"), pos=wpos)[:1]:
                    for word in por_lemmas.get(synset_key(synset), [])[:2]:
                        if word not in found:
                            found.append(word)
                            source = "wordnet-pt"
        found = [w for w in found if w and not re.search(r"[а-яё]", w.lower())]
        entry["pt"] = "; ".join(found[:3])
        entry["pt_source"] = source if entry["pt"] else ""
        stats[entry["pt_source"] or "sem"] += 1
    log(f"Traduções: {dict(stats)}")


def synset_key(synset) -> str:
    return f"{synset.offset():08d}-{synset.pos().replace('s', 'a')}"


def load_por_lemmas(cache: Path) -> dict[str, list[str]]:
    lemmas: dict[str, list[str]] = collections.defaultdict(list)
    path = cache / "nltk_data" / "corpora" / "omw-1.4" / "por" / "wn-data-por.tab"
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 3 and parts[1].endswith("lemma"):
            lemmas[parts[0]].append(parts[2].replace("_", " "))
    return lemmas


# ----------------------------------------------------------------------------- temas
STOP_TERMS = {
    "be", "have", "do", "get", "make", "go", "come", "take", "give", "put", "set", "let", "say", "tell", "see",
    "know", "think", "want", "can", "may", "must", "will", "would", "should", "it", "this", "that", "he", "she",
    "we", "they", "you", "one", "all", "any", "some", "no", "not", "yes", "so", "too", "very", "well", "then",
    "here", "there", "now", "only", "just", "also", "even", "still", "already", "more", "most", "less",
    "thing", "way", "kind", "sort", "part", "side", "case", "matter", "point", "place", "time", "people",
    "man", "woman", "person", "good", "bad", "new", "old", "big", "small", "great", "little", "right", "own",
}


class ThemeClassifier:
    def __init__(self, themes: list[dict], wn):
        self.themes = themes
        self.wn = wn
        self.anchor_theme: dict[str, list[str]] = collections.defaultdict(list)
        self.domain_theme: dict[str, list[str]] = collections.defaultdict(list)
        self.lexname_theme: dict[str, list[tuple[str, float]]] = collections.defaultdict(list)
        self.keywords: list[tuple[str, str, bool]] = []
        for theme in themes:
            for name in theme.get("anchors", []):
                self.anchor_theme[name].append(theme["id"])
            for name in theme.get("domains", []):
                self.domain_theme[name].append(theme["id"])
            for lexname, weight in theme.get("lexnames", {}).items():
                self.lexname_theme[lexname].append((theme["id"], float(weight)))
            for keyword in theme.get("keywords", []):
                if "(" in keyword:
                    continue
                keyword = keyword.lower()
                self.keywords.append((theme["id"], keyword, " " in keyword or "-" in keyword))
        self._closure_cache: dict[str, set[str]] = {}
        missing = [n for n in list(self.anchor_theme) + list(self.domain_theme) if not self._exists(n)]
        if missing:
            log(f"Aviso: synsets inexistentes em themes.json: {', '.join(sorted(missing))}")

    def _exists(self, name: str) -> bool:
        try:
            self.wn.synset(name)
            return True
        except Exception:  # noqa: BLE001
            return False

    def closure(self, synset) -> set[str]:
        name = synset.name()
        if name not in self._closure_cache:
            names = {name}
            for path in synset.hypernym_paths():
                names.update(s.name() for s in path)
            for inst in synset.instance_hypernyms():
                for path in inst.hypernym_paths():
                    names.update(s.name() for s in path)
            self._closure_cache[name] = names
        return self._closure_cache[name]

    def synset_scores(self, synset, weight: float, scores: collections.Counter) -> None:
        for name in self.closure(synset):
            for theme in self.anchor_theme.get(name, ()):
                scores[theme] += 3.0 * weight
        domains = set()
        for related in [synset] + synset.hypernyms()[:2]:
            domains.update(d.name() for d in related.topic_domains())
        for domain in domains:
            for theme in self.domain_theme.get(domain, ()):
                scores[theme] += 3.0 * weight
            # O próprio domínio pode descender de uma âncora (ex.: domínio "cardiology" sob "medicine").
            try:
                for name in self.closure(self.wn.synset(domain)):
                    for theme in self.domain_theme.get(name, ()):
                        scores[theme] += 1.5 * weight
            except Exception:  # noqa: BLE001
                pass
        for theme, lex_weight in self.lexname_theme.get(synset.lexname(), ()):
            scores[theme] += lex_weight * weight

    def keyword_scores(self, text: str, weight: float, scores: collections.Counter) -> None:
        low = " " + re.sub(r"[^a-z' -]", " ", text.lower()) + " "
        tokens = low.split()
        for theme, keyword, phrase in self.keywords:
            if phrase:
                if f" {keyword} " in low:
                    scores[theme] += 2.0 * weight
                continue
            for token in tokens:
                if token == keyword or (len(keyword) >= 5 and token.startswith(keyword)):
                    scores[theme] += 1.6 * weight
                    break

    def classify(self, entry: dict, sense_glosses: list[str]) -> list[tuple[str, float]]:
        scores: collections.Counter = collections.Counter()
        terms = gloss_terms(entry["en"], entry["pos"])
        # Palavras gramaticais (я = "I", он = "he", у = "at") não passam pelo WordNet:
        # lá "I" é iodo e "he" é hélio. Só advérbios de verdade são consultados.
        wpos = WN_POS[entry["pos"]] or "r"
        for t_index, term in enumerate(terms[:4]):
            t_weight = 1.0 if t_index == 0 else 0.6
            self.keyword_scores(term, t_weight, scores)
            if len(term) < 3 or term.lower() in STOP_TERMS:
                continue
            synsets = self.wn.synsets(term.replace(" ", "_"), pos=wpos)
            for s_index, synset in enumerate(synsets[:2]):
                s_weight = t_weight * (1.0 if s_index == 0 else 0.35)
                self.synset_scores(synset, s_weight, scores)
                # Adjetivos e verbos herdam o tema do substantivo de que derivam (scientific -> science).
                for lemma in synset.lemmas()[:2]:
                    related = lemma.pertainyms() + (lemma.derivationally_related_forms() if wpos in ("v", "a") else [])
                    for rel in related[:2]:
                        if rel.synset().pos() == "n":
                            self.synset_scores(rel.synset(), s_weight * 0.6, scores)
        for gloss in sense_glosses[:3]:
            self.keyword_scores(gloss, 0.5, scores)
            match = re.match(r"([a-z ]+):", gloss)
            if match:  # rótulo de domínio do Wiktionary: "politics: ...", "medicine: ..."
                self.keyword_scores(match.group(1), 1.5, scores)
        if not scores:
            return []
        best = max(scores.values())
        chosen = [(t, round(s, 2)) for t, s in scores.most_common() if s >= 2.4 and s >= best * 0.45]
        return chosen[:3]


def load_core(path: Path) -> dict[tuple[str, str], tuple[str, list[str]]]:
    """data/curation/core_lexicon.tsv: lema, classe, português revisto, temas (x = fora das sessões)."""
    core: dict[tuple[str, str], tuple[str, list[str]]] = {}
    if not path.exists():
        return core
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        core[(plain(parts[0]), parts[1].strip())] = (parts[2].strip(), [t.strip() for t in parts[3].split(",") if t.strip()])
    return core


def apply_core(entries: list[dict], core: dict) -> None:
    applied = 0
    for entry in entries:
        found = core.get((plain(entry["lemma"]), entry["pos"]))
        if not found:
            continue
        pt, themes = found
        if pt:
            entry["pt"], entry["pt_source"] = pt, "curadoria"
        if "x" in themes:
            entry["exclude"] = True
        entry["themes"] = [(t, 9.0) for t in themes if t != "x"] or entry["themes"]
        entry["curated"] = True
        applied += 1
    log(f"Curadoria aplicada: {applied} verbetes")


def assign_themes(entries, ru_table, classifier, theme_overrides) -> None:
    glosses_for: dict[str, list[str]] = collections.defaultdict(list)
    for (head, pos, sense), words in ru_table.items():
        for word in words:
            glosses_for[plain(word)].append(f"{sense} {head}")
    counts = collections.Counter()
    for number, entry in enumerate(entries, start=1):
        if number % 10000 == 0:
            log(f"  temas: {number}/{len(entries)}")
        if entry.get("curated"):
            continue
        themes = classifier.classify(entry, glosses_for.get(plain(entry["lemma"]), []))
        names = [t for t, _ in themes]
        # Palavras gramaticais e de altíssima frequência formam o eixo "Essencial".
        if entry["rank"] <= 1500 and themes and themes[0][1] < 4.5:
            themes = []
        if entry["pos"] == "other" and entry["rank"] <= 4000:
            themes.insert(0, ("essencial", 5.0))
        elif (not themes and entry["rank"] <= 4000) or entry["rank"] <= 600:
            themes.append(("essencial", 2.0))
        key = (plain(entry["lemma"]), entry["pos"])
        for change in theme_overrides.get(key, []):
            if change.startswith("-"):
                themes = [t for t in themes if t[0] != change[1:]]
            else:
                theme = change.lstrip("+")
                themes = [t for t in themes if t[0] != theme]
                themes.insert(0, (theme, 9.0))
        seen, final = set(), []
        for theme, score in themes:
            if theme not in seen:
                seen.add(theme)
                final.append((theme, score))
        entry["themes"] = final[:3]
    propagate_by_root(entries)
    for entry in entries:
        if not entry["themes"]:
            entry["themes"] = [("geral", 1.0)]
        for theme, _ in entry["themes"]:
            counts[theme] += 1
    log(f"Palavras por tema: {dict(counts.most_common())}")


ROOT_ENDINGS = re.compile(r"(ться|тись|ть|ти|чь|ость|ение|ание|ство|ский|ской|ный|ной|ий|ый|ой|ая|ое|ие|ия|ья|ь|а|я|о|е|ы|и|й)$")


def root_of(lemma: str) -> str:
    return ROOT_ENDINGS.sub("", plain(lemma))


def propagate_by_root(entries: list[dict]) -> None:
    """Palavra sem tema herda o tema de uma palavra mais frequente de mesma raiz (учительница <- учитель)."""
    roots: dict[str, list[tuple[str, float]]] = {}
    for entry in sorted(entries, key=lambda e: e["rank"]):
        themed = [(t, s) for t, s in entry["themes"] if t not in ("essencial", "geral")]
        root = root_of(entry["lemma"])
        if themed and len(root) >= 6 and root not in roots:
            roots[root] = themed
    inherited = 0
    for entry in entries:
        if entry.get("curated") or any(t not in ("essencial", "geral") for t, _ in entry["themes"]) or entry["rank"] <= 1500:
            continue
        word = plain(entry["lemma"])
        for size in range(len(word) - 1, 5, -1):
            found = roots.get(word[:size])
            if found:
                entry["themes"] = [t for t in entry["themes"] if t[0] == "essencial"] + [(t, round(s * 0.6, 2)) for t, s in found[:2]]
                inherited += 1
                break
    log(f"Temas herdados pela raiz: {inherited}")


# ----------------------------------------------------------------------------- expressões
def build_expressions(ru_table, pt_table, entries, classifier, form_owner) -> list[dict]:
    by_id = {e["id"]: e for e in entries}
    expressions, seen = [], set()
    for key, ru_words in ru_table.items():
        head, pos, sense = key
        if key not in pt_table:
            continue
        phrase_like = " " in head or pos in {"phrase", "proverb", "idiom", "interj"}
        if not phrase_like:
            continue
        pt_words = [w for w in pt_table[key] if " " in w or pos in {"interj", "phrase", "proverb"}]
        if not pt_words:
            pt_words = pt_table[key][:1]
        for ru in ru_words[:2]:
            if " " not in ru or not re.fullmatch(r"[а-яёА-ЯЁ ,!?\-—–.]+", ru) or len(ru.split()) > 9:
                continue
            ident = plain(ru)
            if ident in seen:
                continue
            seen.add(ident)
            tokens = [plain(t) for t in re.findall(r"[а-яёА-ЯЁ\-]+", ru)]
            ranks, scores = [], collections.Counter()
            for token in tokens:
                owner = form_owner.get(token)
                if owner:
                    entry = by_id[owner]
                    ranks.append(entry["rank"])
                    if entry["pos"] != "other":
                        for theme, score in entry["themes"]:
                            if theme != "essencial":
                                scores[theme] += 1
            classifier.keyword_scores(f"{head} {sense}", 1.0, scores)
            themes = [t for t, s in scores.most_common(2) if s >= 1.5] or ["essencial"]
            difficulty = max(ranks) if ranks else 50000
            expressions.append({
                "ru": ru, "pt": "; ".join(pt_words[:2]), "en": head, "sense": sense,
                "kind": pos, "themes": themes, "rank": difficulty,
            })
    expressions.sort(key=lambda e: e["rank"])
    for number, expression in enumerate(expressions, start=1):
        expression["id"] = number
    log(f"Expressões: {len(expressions)}")
    return expressions


# ----------------------------------------------------------------------------- conteúdo existente
THEMED_UNITS = {
    "u07": ["educacao"], "u08": ["trabalho"], "u09": ["ciencia"], "u10": ["midia"], "u11": ["sociedade"],
    "u15": ["viagem"], "u16": ["viagem"], "u20": ["quantidade"], "u22": ["tempo"],
    "v07": ["educacao"], "v08": ["trabalho"], "v09": ["ciencia"], "v10": ["midia"], "v11": ["sociedade"],
    "v06": ["sociedade"], "v15": ["viagem"], "v16": ["viagem"], "v20": ["quantidade"], "v22": ["tempo"],
}


GENERIC_THEMES = {"linguagem", "quantidade", "tempo", "emocoes", "viagem"}


def map_content(entries, form_owner) -> list[tuple[str, str, float]]:
    """Distribui exercícios de gramática e construções já escritos pelos temas, pelo vocabulário que usam."""
    by_id = {e["id"]: e for e in entries}

    def text_themes(text: str) -> collections.Counter:
        scores = collections.Counter()
        for token in re.findall(r"[а-яёА-ЯЁ\-]+", text):
            owner = form_owner.get(plain(token))
            if not owner:
                continue
            entry = by_id[owner]
            if entry["pos"] == "other" or entry["rank"] < 150:
                continue
            for theme, score in entry["themes"]:
                if theme not in ("essencial", "geral"):
                    # Temas transversais (pensamento, quantidade, tempo) aparecem em quase toda frase;
                    # pesam menos para que o exercício vá para o campo temático de verdade.
                    weight = 0.4 if theme in GENERIC_THEMES else 1.0
                    if entry["pos"] == "verb":
                        weight *= 0.5  # verbos de movimento e de fala estão em quase toda frase
                    scores[theme] += weight * min(score, 6.0) / 6.0
        return scores

    rows: list[tuple[str, str, float]] = []
    for path in sorted((DATA / "units").glob("*.json")):
        unit = json.loads(path.read_text(encoding="utf-8"))
        if unit.get("course_id", "russian") != "russian":
            continue
        prefix = unit["id"].split("_")[0]
        for exercise in unit.get("exercises", []):
            text = json.dumps(exercise, ensure_ascii=False)
            scores = text_themes(text)
            for theme in THEMED_UNITS.get(prefix, []):
                scores[theme] += 10
            picked = [(t, s) for t, s in scores.most_common(2) if s >= 1.0] or [("essencial", 1.0)]
            rows.extend((exercise["id"], t, round(s, 2)) for t, s in picked)
    for path in sorted((DATA / "vocab_lessons").glob("*.json")):
        lesson = json.loads(path.read_text(encoding="utf-8"))
        for item in lesson.get("items", []):
            text = json.dumps(item, ensure_ascii=False)
            scores = text_themes(text)
            for theme in THEMED_UNITS.get(lesson["id"], []):
                scores[theme] += 10
            picked = [(t, s) for t, s in scores.most_common(2) if s >= 1.0] or [("essencial", 1.0)]
            rows.extend((f"{lesson['id']}:{item['key']}", t, round(s, 2)) for t, s in picked)
    prefix = json.loads((DATA / "prefix_verbs.json").read_text(encoding="utf-8"))
    for exercise in prefix.get("exercises", []):
        scores = text_themes(json.dumps(exercise, ensure_ascii=False))
        picked = [(t, s) for t, s in scores.most_common(1) if s >= 1.0] or [("essencial", 1.0)]
        rows.extend((exercise["id"], t, round(s, 2)) for t, s in picked)
    log(f"Conteúdo existente distribuído: {len({r[0] for r in rows})} itens")
    return rows


# ----------------------------------------------------------------------------- curadoria
def read_overrides(path: Path, multi: bool = False) -> dict:
    result: dict = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        key = (plain(parts[0]), parts[1].strip())
        if multi:
            result[key] = [p.strip() for p in parts[2].split(",") if p.strip()]
        else:
            result[key] = parts[2].strip()
    return result


# ----------------------------------------------------------------------------- saída
OFFENSIVE = re.compile(r"vulgar|obscen|offensive|derogatory|slur|taboo|swear", re.I)


def studyable(entry: dict) -> bool:
    """Entra nas sessões de estudo: tem tradução, não é nome próprio nem palavrão."""
    if not entry.get("pt") or entry.get("exclude"):
        return False
    if entry["lemma"][:1].isupper() or OFFENSIVE.search(entry["en"] or ""):
        return False
    return True

def write_database(entries, expressions, content_rows, themes, target: Path) -> None:
    temporary = target.with_suffix(".tmp")
    raw = temporary.with_suffix(".sqlite3")
    raw.unlink(missing_ok=True)
    conn = sqlite3.connect(raw)
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, lemma TEXT NOT NULL, accented TEXT, pos TEXT NOT NULL,
            rank INTEGER NOT NULL, level TEXT NOT NULL, freq REAL,
            pt TEXT, pt_source TEXT, en TEXT, study INTEGER NOT NULL DEFAULT 1,
            gender TEXT, animate INTEGER, indeclinable INTEGER, sg_only INTEGER, pl_only INTEGER,
            aspect TEXT, partner TEXT, forms TEXT
        );
        CREATE TABLE entry_themes (entry_id INTEGER NOT NULL, theme_id TEXT NOT NULL, score REAL, PRIMARY KEY (entry_id, theme_id));
        CREATE TABLE expressions (id INTEGER PRIMARY KEY, ru TEXT, pt TEXT, en TEXT, sense TEXT, kind TEXT, rank INTEGER);
        CREATE TABLE expression_themes (expression_id INTEGER NOT NULL, theme_id TEXT NOT NULL, PRIMARY KEY (expression_id, theme_id));
        CREATE TABLE content_themes (item_id TEXT NOT NULL, theme_id TEXT NOT NULL, score REAL, PRIMARY KEY (item_id, theme_id));
        CREATE TABLE themes (id TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(
            e["id"], e["lemma"], e["accented"], e["pos"], e["rank"], e["level"], e["freq"],
            e.get("pt", ""), e.get("pt_source", ""), e["en"], int(studyable(e)), e["gender"], int(e["animate"]),
            int(e["indeclinable"]), int(e["sg_only"]), int(e["pl_only"]), e["aspect"], e["partner"],
            json.dumps(e["forms"], ensure_ascii=False),
        ) for e in entries],
    )
    conn.executemany(
        "INSERT INTO entry_themes VALUES (?,?,?)",
        [(e["id"], theme, score) for e in entries for theme, score in e["themes"]],
    )
    conn.executemany(
        "INSERT INTO expressions VALUES (?,?,?,?,?,?,?)",
        [(x["id"], x["ru"], x["pt"], x["en"], x["sense"], x["kind"], x["rank"]) for x in expressions],
    )
    conn.executemany(
        "INSERT INTO expression_themes VALUES (?,?)",
        [(x["id"], t) for x in expressions for t in x["themes"]],
    )
    conn.executemany("INSERT OR IGNORE INTO content_themes VALUES (?,?,?)", content_rows)
    conn.executemany(
        "INSERT INTO themes VALUES (?,?)",
        [(t["id"], json.dumps({k: t[k] for k in ("id", "name", "ru", "icon", "color", "description")}, ensure_ascii=False)) for t in themes],
    )
    conn.executescript(
        """
        CREATE INDEX idx_theme ON entry_themes(theme_id, entry_id);
        CREATE INDEX idx_rank ON entries(rank);
        CREATE INDEX idx_expr_theme ON expression_themes(theme_id);
        CREATE INDEX idx_content_theme ON content_themes(theme_id);
        """
    )
    conn.executemany("INSERT INTO metadata VALUES (?,?)", [
        ("entries", str(len(entries))),
        ("expressions", str(len(expressions))),
        ("sources", "OpenRussian (CC BY-SA 4.0); FrequencyWords/OpenSubtitles (CC BY-SA 4.0); "
                    "Wiktionary via Open DSL Dictionary Project (CC BY-SA 3.0); Princeton WordNet 3.0; OpenWN-PT (CC BY-SA)"),
    ])
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    with open(raw, "rb") as source, gzip.open(temporary, "wb", compresslevel=9) as out:
        shutil.copyfileobj(source, out)
    temporary.replace(target)
    raw.unlink(missing_ok=True)
    log(f"Gravado {target} ({target.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", default=str(BASE / ".cache" / "lexicon"))
    parser.add_argument("--out", default=str(OUTPUT))
    args = parser.parse_args()
    cache = Path(args.cache)
    fetch(cache)
    os.environ["NLTK_DATA"] = str(cache / "nltk_data")
    from nltk.corpus import wordnet as wn  # noqa: PLC0415 - só na construção

    wn.ensure_loaded()
    themes = json.loads((DATA / "themes.json").read_text(encoding="utf-8"))["themes"]
    log("Lendo OpenRussian...")
    entries = load_openrussian(cache)
    compute_ranks(entries, load_frequencies(cache))
    log("Lendo Wiktionary...")
    ru_table = load_wiktionary(cache / "en-ru.txt")
    pt_table = load_wiktionary(cache / "en-pt.txt")
    portuguese_candidates(
        entries, ru_table, pt_table, wn, load_por_lemmas(cache),
        read_overrides(DATA / "curation" / "pt_overrides.tsv"),
    )
    log("Classificando por tema...")
    for entry in entries:
        entry["themes"] = []
    apply_core(entries, load_core(DATA / "curation" / "core_lexicon.tsv"))
    classifier = ThemeClassifier(themes, wn)
    assign_themes(entries, ru_table, classifier, read_overrides(DATA / "curation" / "theme_overrides.tsv", multi=True))
    form_owner: dict[str, int] = {}
    for entry in sorted(entries, key=lambda e: e["rank"]):
        for form in [entry["lemma"], *[v for value in entry["forms"].values() for v in split_top(value, ",")]]:
            form_owner.setdefault(plain(form), entry["id"])
    expressions = build_expressions(ru_table, pt_table, entries, classifier, form_owner)
    content_rows = map_content(entries, form_owner)
    write_database(entries, expressions, content_rows, themes, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
