"""Integração oficial com a Steam Web API.

Este módulo centraliza todas as chamadas oficiais da Steam e evita depender
completamente da página pública do perfil para montar a biblioteca do usuário.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str, max_age_seconds: int = 900) -> Any | None:
    _ensure_cache_dir()
    path = _cache_path(name)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and "timestamp" in payload and "data" in payload:
            if time.time() - payload["timestamp"] <= max_age_seconds:
                return payload["data"]
    except Exception:
        return None

    return None


def _write_cache(name: str, data: Any) -> None:
    _ensure_cache_dir()
    path = _cache_path(name)
    payload = {"timestamp": time.time(), "data": data}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _steam_fetch_json(url: str, timeout: int = 15, cache_key: str | None = None, cache_ttl: int = 900) -> Any:
    if cache_key:
        cached = _read_cache(cache_key, cache_ttl)
        if cached is not None:
            return cached

    request = Request(
        url,
        headers={
            "User-Agent": "GameLink/2.0",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://store.steampowered.com/",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as resposta:
            corpo = resposta.read().decode("utf-8", errors="replace")
            dados = json.loads(corpo)
            if cache_key:
                _write_cache(cache_key, dados)
            return dados
    except Exception:
        if cache_key:
            cached = _read_cache(cache_key, 0)
            if cached is not None:
                return cached
        return {}


def obter_perfil(steam_id64: str, api_key: str = "") -> Dict[str, Any]:
    if not steam_id64:
        return {}

    if not api_key:
        return {"steamid": steam_id64, "personaname": "Steam", "avatar": "", "profileurl": f"https://steamcommunity.com/profiles/{steam_id64}"}

    url = (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?"
        f"key={quote(api_key)}&steamids={quote(steam_id64)}&format=json"
    )
    dados = _steam_fetch_json(url, cache_key=f"profile_{steam_id64}", cache_ttl=1800)
    players = (dados.get("response", {}) or {}).get("players", []) or []
    if not players:
        return {"steamid": steam_id64, "personaname": "Steam", "avatar": "", "profileurl": f"https://steamcommunity.com/profiles/{steam_id64}"}

    player = players[0]
    return {
        "steamid": player.get("steamid", steam_id64),
        "personaname": player.get("personaname") or "Steam",
        "avatar": player.get("avatarfull") or player.get("avatar") or "",
        "profileurl": player.get("profileurl") or f"https://steamcommunity.com/profiles/{steam_id64}",
        "personastate": player.get("personastate"),
        "gameextrainfo": player.get("gameextrainfo"),
        "gameid": player.get("gameid"),
    }


def obter_jogos(steam_id64: str, api_key: str = "") -> List[Dict[str, Any]]:
    if not steam_id64 or not api_key:
        return []

    url = (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?"
        f"key={quote(api_key)}&steamid={quote(steam_id64)}"
        "&include_appinfo=1&include_played_free_games=1&format=json"
    )
    dados = _steam_fetch_json(url, cache_key=f"owned_games_{steam_id64}", cache_ttl=1800)
    jogos = (dados.get("response", {}) or {}).get("games", []) or []
    resultado: List[Dict[str, Any]] = []
    for jogo in jogos:
        appid = jogo.get("appid")
        if not appid:
            continue
        resultado.append(
            {
                "appid": int(appid),
                "name": jogo.get("name") or f"App {appid}",
                "playtime_forever": int(jogo.get("playtime_forever") or 0),
                "playtime_2weeks": int(jogo.get("playtime_2weeks") or 0),
                "img_icon_url": jogo.get("img_icon_url") or "",
                "img_logo_url": jogo.get("img_logo_url") or "",
            }
        )
    return resultado


def obter_status(steam_id64: str, api_key: str = "") -> Dict[str, Any]:
    perfil = obter_perfil(steam_id64, api_key)
    if not perfil:
        return {"online": False, "game": "", "appid": None}

    personastate = int(perfil.get("personastate") or 0)
    return {
        "online": personastate != 0,
        "game": perfil.get("gameextrainfo") or "",
        "appid": int(perfil.get("gameid") or 0) if perfil.get("gameid") else None,
        "personaname": perfil.get("personaname") or "Steam",
        "avatar": perfil.get("avatar") or "",
    }


def obter_horas(steam_id64: str, api_key: str = "") -> int:
    jogos = obter_jogos(steam_id64, api_key)
    return int(sum(int(j.get("playtime_forever") or 0) for j in jogos) / 60)


def obter_avatar(steam_id64: str, api_key: str = "") -> str:
    perfil = obter_perfil(steam_id64, api_key)
    return perfil.get("avatar") or ""


def obter_conquistas(steam_id64: str, api_key: str, appid: int) -> Dict[str, Any]:
    if not steam_id64 or not api_key or not appid:
        return {}

    url = (
        "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/?"
        f"key={quote(api_key)}&steamid={quote(steam_id64)}&appid={appid}&l=pt-BR"
    )
    dados = _steam_fetch_json(url, cache_key=f"achievements_{steam_id64}_{appid}", cache_ttl=1800)
    return dados.get("playerstats", {}) or {}


def obter_estatisticas(steam_id64: str, api_key: str, appid: int) -> Dict[str, Any]:
    if not steam_id64 or not api_key or not appid:
        return {}

    url = (
        "https://api.steampowered.com/ISteamUserStats/GetUserStatsForGame/v2/?"
        f"key={quote(api_key)}&steamid={quote(steam_id64)}&appid={appid}&l=pt-BR"
    )
    dados = _steam_fetch_json(url, cache_key=f"stats_{steam_id64}_{appid}", cache_ttl=1800)
    return dados.get("playerstats", {}) or {}


def obter_amigos(steam_id64: str, api_key: str = "") -> List[Dict[str, Any]]:
    if not steam_id64 or not api_key:
        return []

    url = (
        "https://api.steampowered.com/ISteamUser/GetFriendList/v1/?"
        f"key={quote(api_key)}&steamid={quote(steam_id64)}&relationship=friend"
    )
    dados = _steam_fetch_json(url, cache_key=f"friends_{steam_id64}", cache_ttl=1800)
    amigos = (dados.get("friendslist", {}) or {}).get("friends", []) or []
    return amigos


def obter_jogo(appid: int) -> Dict[str, Any]:
    if not appid:
        return {}

    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=br&l=pt"
    dados = _steam_fetch_json(url, cache_key=f"store_{appid}", cache_ttl=86400)
    item = (dados or {}).get(str(appid), {}) or {}
    if not item.get("success"):
        return {}
    dados_jogo = item.get("data", {}) or {}
    return {
        "appid": int(appid),
        "name": dados_jogo.get("name") or f"App {appid}",
        "header_image": dados_jogo.get("header_image") or "",
        "capsule_image": dados_jogo.get("capsule_image") or "",
        "background": dados_jogo.get("background") or "",
        "short_description": dados_jogo.get("short_description") or "",
        "genres": dados_jogo.get("genres") or [],
    }
