# -*- mode: python ; coding: utf-8 -*-
# Gera dist/RussoTrainer/ (RussoTrainer.exe + _internal). Use packaging/build_windows.ps1.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent

# Só conteúdo somente-leitura. Progresso, exports e cache de áudio ficam em %APPDATA%.
datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "data" / "units"), "data/units"),
    (str(ROOT / "data" / "vocab_lessons"), "data/vocab_lessons"),
    (str(ROOT / "data" / "course_lexicon.json"), "data"),
    (str(ROOT / "data" / "prefix_verbs.json"), "data"),
    (str(ROOT / "data" / "openrussian.sqlite3"), "data"),
    (str(ROOT / "data" / "lexical_minimum.sqlite3"), "data"),
    (str(ROOT / "third_party"), "third_party"),
]
binaries = []
hiddenimports = []
for package in ("edge_tts",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RussoTrainer",
    console=True,  # a janela mostra o log e fechá-la encerra o app
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RussoTrainer", upx=False)
