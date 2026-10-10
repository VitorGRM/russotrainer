#!/usr/bin/env python3
"""Gera antecipadamente o áudio das aulas narradas e o guarda em data/tts_cache.

A primeira reprodução de uma aula inteira leva cerca de um minuto para ser
sintetizada pelo edge-tts. Rodando este script uma vez (com internet), todas as
aulas já ficam prontas e passam a tocar instantaneamente, inclusive offline.

    ./.venv/bin/python tools/pregenerate_audio.py            # tudo
    ./.venv/bin/python tools/pregenerate_audio.py --blocks   # só os blocos
    ./.venv/bin/python tools/pregenerate_audio.py u12 u13    # só estas unidades
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402
from vocab_lessons import VocabLessonStore  # noqa: E402


def vocabulary_targets(fragments: list[str]) -> list[tuple[str, str, str]]:
    """Enumerate exactly the text/voice pairs requested by the vocabulary UI."""
    store = VocabLessonStore(Path(__file__).resolve().parents[1] / "data" / "vocab_lessons")
    store.load()
    targets: dict[tuple[str, str], str] = {}
    for lesson in store.lessons:
        if fragments and not any(f in lesson["id"] or f in lesson["unit_id"] for f in fragments):
            continue
        def add(text: str, voice: str, role: str) -> None:
            targets.setdefault((text, voice), f"{lesson['id']} · {role}")
        for line in lesson["dialogue"]["lines"]:
            add(line["ru"], store.voice_of(lesson, line["speaker"]), "diálogo")
        for index, item in enumerate(lesson["items"]):
            add(item["head"], "", "cabeçalho")
            add(item["chunk"], "", "cartão")
            add(item["chunk"], "f", "construção")
            add(item["example"]["ru"], "f", "exemplo")
            add(item["hear"]["ru"], "m" if index % 2 else "f", "escuta")
        # Includes native-rate recognition clips, cloze answers, reconstructed
        # lines and both sides of the replies, including all after_audio voices.
        for exercise in lesson["generated"]:
            if exercise.get("audio_text"):
                add(exercise["audio_text"], exercise.get("voice", ""), exercise["id"])
            if exercise.get("after_audio"):
                audio = exercise["after_audio"]
                add(audio["text"], audio.get("voice", ""), exercise["id"])
    return [(label, text, voice) for (text, voice), label in targets.items()]


def pregenerate_vocabulary(fragments: list[str], workers: int) -> int:
    targets = vocabulary_targets(fragments)
    if not targets:
        print("Nenhuma lição de vocabulário encontrada.")
        return 1
    print(f"{len(targets)} áudios de vocabulário a verificar.", flush=True)
    def generate(target):
        label, text, voice = target
        started = time.monotonic()
        # Jobs have distinct cache keys; each owns its TTS lock and temp file.
        for attempt in range(3):
            try:
                path = app.TTSService(app.TTS_CACHE_DIR).audio_for(text, "russian", speaker=voice)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(.5 * (attempt + 1))
        return label, path.stat().st_size, time.monotonic() - started
    failed = cached = generated = 0
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(generate, target): target for target in targets}
        for position, future in enumerate(as_completed(pending), 1):
            try:
                label, size, elapsed = future.result()
                cached += elapsed < .5
                generated += elapsed >= .5
                status = "já em cache" if elapsed < .5 else f"gerado ({size} bytes)"
                print(f"[{position}/{len(targets)}] {label}: {status}", flush=True)
            except Exception as exc:
                failed += 1
                print(f"[{position}/{len(targets)}] {pending[future][0]}: FALHOU — {exc}", flush=True)
    print(f"{generated} gerados · {cached} já em cache · {failed} falhas · {(time.monotonic()-started)/60:.1f} min", flush=True)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pré-gera as narrações das aulas.")
    parser.add_argument("units", nargs="*", help="ids (ou fragmentos de id) de unidades; vazio = todas")
    parser.add_argument("--blocks", action="store_true", help="gerar só os blocos, não a aula inteira")
    parser.add_argument("--full", action="store_true", help="gerar só a aula inteira, não os blocos")
    parser.add_argument("--vocab", action="store_true", help="gerar diálogos, construções, exemplos, escutas e réplicas do curso russo")
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9), help="gerações simultâneas de vocabulário (1–8; padrão 4)")
    args = parser.parse_args()
    if args.vocab:
        return pregenerate_vocabulary(args.units, args.workers)

    content = app.ContentStore(app.UNITS_DIR)
    tts = app.TTSService(app.TTS_CACHE_DIR)

    targets: list[tuple[dict, int | None]] = []
    for unit in content.units:
        if args.units and not any(fragment in unit["id"] for fragment in args.units):
            continue
        blocks = unit.get("grammar") or []
        if not blocks:
            continue
        if not args.full:
            targets.extend((unit, index) for index in range(len(blocks)))
        if not args.blocks:
            targets.append((unit, None))

    if not targets:
        print("Nenhuma aula encontrada para os filtros informados.")
        return 1

    print(f"{len(targets)} arquivos de áudio a verificar.\n")
    generated = cached = failed = 0
    started = time.time()
    for position, (unit, block) in enumerate(targets, start=1):
        label = f"{unit['id']} · {'aula inteira' if block is None else f'bloco {block}'}"
        try:
            script = app.lesson_script(unit, block)
        except ValueError as exc:
            print(f"[{position}/{len(targets)}] {label}: ignorado ({exc})")
            continue
        mark = time.time()
        try:
            path = tts.audio_for(script, unit.get("course_id", "russian"), mode="lesson")
        except Exception as exc:  # rede indisponível, texto longo demais etc.
            failed += 1
            print(f"[{position}/{len(targets)}] {label}: FALHOU — {exc}")
            continue
        elapsed = time.time() - mark
        if elapsed < 0.5:
            cached += 1
            print(f"[{position}/{len(targets)}] {label}: já em cache")
        else:
            generated += 1
            size = path.stat().st_size / 1_000_000
            print(f"[{position}/{len(targets)}] {label}: gerado em {elapsed:.0f}s ({size:.1f} MB)")

    total = time.time() - started
    print(f"\n{generated} gerados · {cached} já em cache · {failed} falhas · {total / 60:.1f} min")
    print(f"Cache: {app.TTS_CACHE_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
