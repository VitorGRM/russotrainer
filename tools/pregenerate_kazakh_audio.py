"""Gera de uma vez, com o Edge TTS, todos os áudios do curso de cazaque e grava no cache do aplicativo.

Sem isso, cada áudio é gerado na primeira vez que o aluno toca nele (precisa de internet nesse
momento). Com isso, o curso inteiro fica no cache: vozes kk-KZ-AigulNeural e kk-KZ-DauletNeural para o
cazaque e pt-BR-ThalitaMultilingualNeural para a narração das aulas.

    .venv\\Scripts\\python tools\\pregenerate_kazakh_audio.py                  # cache do app instalado
    .venv\\Scripts\\python tools\\pregenerate_kazakh_audio.py --data-dir <pasta> # outra pasta de dados
    opções: --only k01,k02 (só essas aulas) · --workers 4

Os MP3 ficam em <pasta de dados>/data/tts_cache e não vão para o repositório.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", help="pasta de dados do aluno (padrão: a do aplicativo)")
    parser.add_argument("--only", default="", help="ids de aulas separados por vírgula")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.data_dir:
        sys.argv = [sys.argv[0], "--data-dir", args.data_dir]  # app.py lê --data-dir na importação

    import app  # noqa: PLC0415 - depende do --data-dir acima
    from kazakh import KazakhContent, all_audio_texts  # noqa: PLC0415

    if app.edge_tts is None:
        sys.exit("O edge-tts não está instalado neste Python (use .venv\\Scripts\\python).")
    content = KazakhContent(app.KAZAKH_DIR)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        content.order = [lid for lid in content.order if lid in only]
    local = threading.local()  # um TTSService por thread: cada um tem a própria trava
    jobs = all_audio_texts(content)
    print(f"{len(jobs)} áudios ({len(content.order)} aulas) → {app.TTS_CACHE_DIR}")

    def run(job: tuple[str, str, str]) -> str:
        text, voice, mode = job
        if not hasattr(local, "tts"):
            local.tts = app.TTSService(app.TTS_CACHE_DIR)
        tts = local.tts
        for attempt in range(3):
            try:
                if mode == "lesson":
                    tts.audio_for(text, mode="lesson")
                else:
                    tts.audio_for(text, speaker=voice, lang="kk")
                return ""
            except Exception as exc:  # noqa: BLE001 - tenta de novo e depois relata
                if attempt == 2:
                    return f"{text[:60]!r}: {exc}"
                time.sleep(2 + attempt * 3)
        return ""

    started = time.monotonic()
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for done, future in enumerate(as_completed(futures), 1):
            error = future.result()
            if error:
                failures.append(error)
            if done % 50 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} ({time.monotonic() - started:.0f} s)", flush=True)
    for failure in failures:
        print("FALHOU", failure)
    print(f"Pronto: {len(jobs) - len(failures)} de {len(jobs)} áudios no cache.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
