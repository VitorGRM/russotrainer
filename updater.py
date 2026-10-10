"""Atualização do .exe a partir dos releases do GitHub.

Fluxo: consulta o último release -> baixa o .zip do Windows -> confere o hash ->
extrai numa pasta temporária -> encerra o app -> um script PowerShell espera o
processo terminar, troca os arquivos da pasta de instalação e reabre o .exe.
O progresso do aluno vive em %APPDATA%\\RussoTrainer e nunca é tocado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

# "dono/repositorio" no GitHub. Pode ser sobrescrito pela variável RUSSO_UPDATE_REPO.
GITHUB_REPO = os.environ.get("RUSSO_UPDATE_REPO", "")
ASSET_SUFFIX = "-windows.zip"
EXE_NAME = "RussoTrainer.exe"
USER_AGENT = "RussoTrainer-updater"
CHECK_CACHE_SECONDS = 600

FROZEN = bool(getattr(sys, "frozen", False))

APPLY_SCRIPT = r"""param([int]$ProcId, [string]$Staging, [string]$Install, [string]$Exe, [string]$Log)
function Log($m) { Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format s), $m) -Encoding UTF8 }
Log "Aguardando o app (PID $ProcId) encerrar"
for ($i = 0; $i -lt 120; $i++) {
    if (-not (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}
Start-Sleep -Seconds 1
if ((Test-Path (Join-Path $Staging 'RussoTrainer.exe')) -and (Test-Path (Join-Path $Install 'RussoTrainer.exe'))) {
    robocopy $Staging $Install /MIR /NFL /NDL /NJH /NJS /NP /R:10 /W:1 | Out-Null
    Log "robocopy terminou com codigo $LASTEXITCODE"
    if ($LASTEXITCODE -lt 8) { Remove-Item $Staging -Recurse -Force -ErrorAction SilentlyContinue }
} else {
    Log "Pastas inesperadas; nada foi copiado"
}
Start-Process -FilePath $Exe -WorkingDirectory $Install
Log "App reaberto"
"""


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    numbers = [int(n) for n in re.findall(r"\d+", str(text).split("-")[0])][:4]
    return tuple(numbers + [0] * (4 - len(numbers)))


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Nenhum release encontrado (o repositório pode ser privado ou ainda não ter releases).") from exc
        if exc.code == 403:
            raise UpdateError("O GitHub limitou as consultas. Tente de novo em alguns minutos.") from exc
        raise UpdateError(f"O GitHub respondeu com erro {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Sem conexão com o GitHub.") from exc


class Updater:
    def __init__(self, current_version: str, user_dir: Path, on_restart: Callable[[], None]):
        self.current = current_version
        self.user_dir = user_dir
        self.on_restart = on_restart
        self._lock = threading.Lock()
        self._checked_at = 0.0
        self._info: dict | None = None
        self._status: dict = {"phase": "idle", "done": 0, "total": 0, "error": ""}

    # ------------------------------------------------------------------ consulta
    def check(self, force: bool = False) -> dict:
        base = {"current": self.current, "frozen": FROZEN, "configured": bool(GITHUB_REPO)}
        if not GITHUB_REPO:
            return {**base, "available": False, "error": "Repositório de atualizações ainda não configurado."}
        with self._lock:
            if not force and self._info and time.time() - self._checked_at < CHECK_CACHE_SECONDS:
                return {**base, **self._info}
        try:
            release = _get_json(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")
        except UpdateError as exc:
            return {**base, "available": False, "error": str(exc)}

        latest = str(release.get("tag_name") or "")
        asset = next((a for a in release.get("assets", []) if str(a.get("name", "")).endswith(ASSET_SUFFIX)), None)
        info = {
            "latest": latest.lstrip("vV"),
            "available": parse_version(latest) > parse_version(self.current) and asset is not None,
            "notes": str(release.get("body") or "")[:4000],
            "page": release.get("html_url", ""),
            "asset": (
                {
                    "name": asset["name"],
                    "url": asset["browser_download_url"],
                    "size": int(asset.get("size") or 0),
                    "digest": str(asset.get("digest") or ""),
                }
                if asset
                else None
            ),
            "error": "" if asset else "O release não tem o arquivo do Windows (*-windows.zip).",
        }
        with self._lock:
            self._info, self._checked_at = info, time.time()
        return {**base, **info}

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _set(self, **values: object) -> None:
        with self._lock:
            self._status.update(values)

    # ------------------------------------------------------------------ aplicação
    def start_apply(self) -> None:
        if not FROZEN:
            raise UpdateError("A atualização automática só funciona no aplicativo instalado (.exe).")
        with self._lock:
            if self._status["phase"] in {"downloading", "installing", "restarting"}:
                return
            info = self._info
        if not info or not info.get("available") or not info.get("asset"):
            raise UpdateError("Verifique as atualizações antes de atualizar.")
        self._set(phase="downloading", done=0, total=info["asset"]["size"], error="")
        threading.Thread(target=self._run, args=(info["asset"],), daemon=True).start()

    def _run(self, asset: dict) -> None:
        try:
            work = Path(tempfile.gettempdir()) / "RussoTrainer-update"
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
            archive = work / "release.zip"
            self._download(asset, archive)

            self._set(phase="installing")
            staging = work / "staged"
            self._extract(archive, staging)
            archive.unlink(missing_ok=True)
            root = next((p.parent for p in [staging / EXE_NAME, *staging.glob(f"*/{EXE_NAME}")] if p.exists()), None)
            if root is None:
                raise UpdateError(f"O pacote baixado não contém {EXE_NAME}.")

            self._launch_apply_script(root)
            self._set(phase="restarting")
            time.sleep(0.8)
            self.on_restart()
        except Exception as exc:  # noqa: BLE001 - qualquer falha precisa chegar na interface
            self._set(phase="error", error=str(exc) or exc.__class__.__name__)

    def _download(self, asset: dict, target: Path) -> None:
        request = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
        sha = hashlib.sha256()
        try:
            with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as out:
                while chunk := response.read(1024 * 256):
                    out.write(chunk)
                    sha.update(chunk)
                    self._set(done=self._status["done"] + len(chunk))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError("O download foi interrompido. Tente novamente.") from exc
        expected = asset["digest"].removeprefix("sha256:").lower()
        if expected and sha.hexdigest() != expected:
            raise UpdateError("O arquivo baixado não confere com o hash publicado no GitHub; nada foi instalado.")

    @staticmethod
    def _extract(archive: Path, destination: Path) -> None:
        destination.mkdir(parents=True)
        base = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                if not (base / member).resolve().is_relative_to(base):
                    raise UpdateError("O pacote contém caminhos inválidos; nada foi instalado.")
            bundle.extractall(destination)

    def _launch_apply_script(self, staged_root: Path) -> None:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        script = self.user_dir / "apply_update.ps1"
        script.write_text(APPLY_SCRIPT, encoding="utf-8-sig")
        exe = Path(sys.executable)
        subprocess.Popen(  # noqa: S603 - comando fixo, caminhos são locais
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-File", str(script),
                "-ProcId", str(os.getpid()),
                "-Staging", str(staged_root),
                "-Install", str(exe.parent),
                "-Exe", str(exe),
                "-Log", str(self.user_dir / "update.log"),
            ],
            creationflags=0x08000000 | 0x00000200,  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            close_fds=True,
        )
