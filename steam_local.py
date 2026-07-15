"""Leitura oficial de bibliotecas Steam a partir de arquivos locais.

Este módulo detecta instalações da Steam e appmanifest_*.acf sem depender
de scraping ou da página pública do perfil.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List


def _normalizar_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)) if path else ""


def _buscar_steam_executavel() -> str | None:
    candidatos = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Steam\steam.exe"),
        os.path.expandvars(r"%ProgramFiles%\Steam\steam.exe"),
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
        r"D:\Steam\steam.exe",
        r"E:\Steam\steam.exe",
    ]
    for candidato in candidatos:
        if os.path.exists(candidato):
            return candidato
    return None


def _ler_libraryfolders_vdf(steam_root: str) -> List[str]:
    if not steam_root:
        return []

    libraryfolders = Path(steam_root) / "steamapps" / "libraryfolders.vdf"
    if not libraryfolders.exists():
        return [steam_root]

    try:
        texto = libraryfolders.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [steam_root]

    bibliotecas: List[str] = []
    for match in re.finditer(r'"([A-Za-z]:\\[^"\n]+)"', texto):
        bibliotecas.append(match.group(1).replace('\\', '\\'))
    if not bibliotecas:
        bibliotecas.append(steam_root)
    return bibliotecas


def localizar_bibliotecas_steam() -> List[Dict[str, str]]:
    steam_exe = _buscar_steam_executavel()
    bibliotecas: List[Dict[str, str]] = []
    if steam_exe:
        steam_root = str(Path(steam_exe).parent)
        for biblioteca in _ler_libraryfolders_vdf(steam_root):
            bibliotecas.append({"root": biblioteca, "type": "steam"})
    else:
        bibliotecas.append({"root": r"C:\Program Files (x86)\Steam", "type": "steam"})

    # Evitar duplicações de caminho
    vistas = set()
    resultado: List[Dict[str, str]] = []
    for biblioteca in bibliotecas:
        chave = _normalizar_path(biblioteca["root"])
        if chave in vistas:
            continue
        vistas.add(chave)
        resultado.append(biblioteca)
    return resultado


def listar_jogos_instalados() -> List[Dict[str, str]]:
    jogos: List[Dict[str, str]] = []
    for biblioteca in localizar_bibliotecas_steam():
        root = biblioteca["root"]
        steamapps = Path(root) / "steamapps"
        if not steamapps.exists():
            continue

        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                texto = manifest.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            appid_match = re.search(r'"appid"\s+"(\d+)"', texto)
            name_match = re.search(r'"name"\s+"([^\n]+)"', texto)
            if not appid_match:
                continue

            appid = appid_match.group(1)
            nome = name_match.group(1).strip() if name_match else f"App {appid}"
            jogos.append(
                {
                    "appid": appid,
                    "name": nome,
                    "manifest": str(manifest),
                    "path": str(steamapps / "common" / nome.replace(':', '').replace('\\', '').replace('/', '').strip()),
                    "library": str(Path(root)),
                    "instalado": True,
                }
            )

    return jogos
