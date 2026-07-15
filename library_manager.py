"""Gerenciador unificado de biblioteca Steam/Hydra.

Este módulo une os dados locais da Steam, a Web API oficial e a cache do Hydra
para produzir uma lista final sem duplicação.
"""

from __future__ import annotations

from typing import Dict, List

from steam_api import obter_jogos, obter_perfil, obter_status, obter_jogo
from steam_local import listar_jogos_instalados


def unificar_biblioteca(steam_id64: str, api_key: str = "") -> List[Dict[str, object]]:
    if not steam_id64:
        return []

    jogos_api = obter_jogos(steam_id64, api_key)
    jogos_instalados = listar_jogos_instalados()

    mapa: Dict[int, Dict[str, object]] = {}
    for jogo in jogos_api:
        appid = int(jogo.get("appid") or 0)
        if not appid:
            continue
        mapa[appid] = {
            "source": "steam_api",
            "appid": appid,
            "name": jogo.get("name") or f"App {appid}",
            "playtime_forever": int(jogo.get("playtime_forever") or 0),
            "installed": False,
            "cover_url": "",
            "banner_url": "",
            "header_url": "",
            "launcher": "steam",
            "path": "",
            "library": "",
            "origin": "steam",
            "favorited": False,
            "last_played": None,
            "platform": "PC",
            "steam_id64": steam_id64,
        }

    for jogo_local in jogos_instalados:
        appid = int(jogo_local.get("appid") or 0)
        if not appid:
            continue
        entrada = mapa.get(appid)
        if entrada is None:
            mapa[appid] = {
                "source": "steam_local",
                "appid": appid,
                "name": jogo_local.get("name") or f"App {appid}",
                "playtime_forever": 0,
                "installed": True,
                "cover_url": "",
                "banner_url": "",
                "header_url": "",
                "launcher": "steam",
                "path": jogo_local.get("path") or "",
                "library": jogo_local.get("library") or "",
                "origin": "steam",
                "favorited": False,
                "last_played": None,
                "platform": "PC",
                "steam_id64": steam_id64,
            }
        else:
            entrada["installed"] = True
            entrada["path"] = jogo_local.get("path") or entrada.get("path") or ""
            entrada["library"] = jogo_local.get("library") or entrada.get("library") or ""

    for appid, entrada in mapa.items():
        dados_loja = obter_jogo(int(appid))
        if dados_loja:
            entrada["cover_url"] = dados_loja.get("header_image") or entrada.get("cover_url") or ""
            entrada["banner_url"] = dados_loja.get("background") or entrada.get("banner_url") or ""
            entrada["header_url"] = dados_loja.get("header_image") or entrada.get("header_url") or ""
            entrada["name"] = dados_loja.get("name") or entrada.get("name")

    perfil = obter_perfil(steam_id64, api_key) if api_key else {}
    status = obter_status(steam_id64, api_key) if api_key else {"online": False, "game": "", "appid": None}

    resultado = list(mapa.values())
    resultado.sort(key=lambda item: (int(item.get("playtime_forever") or 0), str(item.get("name") or "")), reverse=True)
    return resultado
