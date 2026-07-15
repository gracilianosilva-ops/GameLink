"""
Script de Validação e Auditoria do Scraping da Biblioteca Steam

Este script permite testar e auditar o scraping de forma isolada,
capturando todos os logs de cada etapa.

Uso:
    python audit_steam_completo.py <steam_id64_ou_url>
    python audit_steam_completo.py 76561198123456789
    python audit_steam_completo.py https://steamcommunity.com/profiles/76561198123456789
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from steam_audit import (
    limpar_log_audit, ler_log_audit, log_import_iniciado,
    log_import_finalizado, log_validacao_banco_dados
)
from app import (
    _steam_resolver_steamid,
    _steam_obter_biblioteca_publica_completa,
    USUARIOS_DB, JOGOS_DB, BIBLIOTECA_DB, GerenciadorBiblioteca
)
from database import get_connection
from urllib.parse import urlparse
import re

def extrair_steamid_de_url(texto: str) -> str:
    """Extrai SteamID64 de uma URL ou retorna o texto como é"""
    
    # Se for URL
    if texto.startswith('http'):
        parsed = urlparse(texto)
        
        # Padrão: /profiles/76561198123456789
        match = re.search(r'/profiles/(\d{17})', parsed.path)
        if match:
            return match.group(1)
        
        # Padrão: /id/vanity_url
        if '/id/' in parsed.path:
            vanity = parsed.path.split('/id/', 1)[1].strip('/')
            return vanity
    
    # Se for um SteamID64 direto (17 dígitos)
    if re.match(r'^\d{17}$', texto):
        return texto
    
    return texto


def auditar_scraping_steam(steam_input: str) -> None:
    """Auditoria completa do scraping de um usuário Steam"""
    
    print("\n" + "="*80)
    print("AUDITORIA COMPLETA DO SCRAPING STEAM")
    print("="*80)
    
    # Limpa log anterior
    limpar_log_audit()
    print("\n[✓] Log de auditoria limpado")
    
    steam_input = extrair_steamid_de_url(steam_input)
    print(f"[✓] Input normalizado: {steam_input}")
    
    # Resolve SteamID
    print("\n" + "-"*80)
    print("ETAPA 1: Resolver SteamID64")
    print("-"*80)
    
    # Tenta usar como SteamID64 direto, senão como vanity URL
    steam_id64 = steam_input if re.match(r'^\d{17}$', steam_input) else None
    
    if not steam_id64:
        print(f"[*] Resolvendo Vanity URL: {steam_input}")
        steam_id64 = _steam_resolver_steamid(steam_input, '')
        if steam_id64:
            print(f"[✓] SteamID64 resolvido: {steam_id64}")
        else:
            print(f"[✗] ERRO: Não foi possível resolver o SteamID64")
            return
    else:
        print(f"[✓] Usando SteamID64 direto: {steam_id64}")
    
    # Busca a biblioteca
    print("\n" + "-"*80)
    print("ETAPA 2: Buscar Biblioteca Pública Completa")
    print("-"*80)
    
    jogos = _steam_obter_biblioteca_publica_completa(steam_id64)
    print(f"[✓] Jogos obtidos: {len(jogos)}")
    
    if len(jogos) > 0:
        print(f"\n[*] Primeiros 10 jogos encontrados:")
        for i, jogo in enumerate(jogos[:10], 1):
            print(f"    {i}. AppID {jogo['appid']:6d} - {jogo['name'][:50]}")
        if len(jogos) > 10:
            print(f"    ... e mais {len(jogos) - 10} jogos")
    else:
        print("[✗] NENHUM JOGO ENCONTRADO!")
    
    # Lê logs
    print("\n" + "-"*80)
    print("ETAPA 3: Log Detalhado da Auditoria")
    print("-"*80)
    
    logs = ler_log_audit()
    print(logs)
    
    # Resumo
    print("\n" + "="*80)
    print("RESUMO DA AUDITORIA")
    print("="*80)
    print(f"SteamID64:              {steam_id64}")
    print(f"Jogos encontrados:      {len(jogos)}")
    print(f"Arquivo de log:         steam_audit.log")
    print("\n[!] Para importar esses jogos para um usuário GameLink:")
    print("    1. Faça login em GameLink")
    print("    2. Vá para Perfil > Conectar Steam")
    print("    3. Cole o SteamID64 ou URL do perfil")
    print("    4. Clique em 'Importar Biblioteca'")
    
    # Valida paginação
    print("\n" + "-"*80)
    print("VALIDAÇÃO: Verificar Paginação")
    print("-"*80)
    
    # Conta quantas páginas deveriam ter sido lidas
    paginas_lidas = logs.count('[PAGINATE_XML]')
    print(f"[*] Páginas processadas: {paginas_lidas}")
    
    if 'totalCount' in str(jogos):
        print("[!] Nota: API pode ter informado total de itens, verificar logs")
    
    # Detecta possíveis problemas
    print("\n" + "-"*80)
    print("DIAGNÓSTICO: Possíveis Problemas")
    print("-"*80)
    
    problemas = []
    
    if len(jogos) == 0:
        problemas.append("Nenhum jogo encontrado - Possível causa: Perfil privado ou biblioteca vazia")
    
    if 'HTTP' in logs and '200' not in logs:
        problemas.append("Problemas na requisição HTTP - Verificar código HTTP nos logs")
    
    if 'ERRO' in logs:
        problemas.append("Erros detectados durante parsing - Verificar logs detalhados")
    
    if problemas:
        for p in problemas:
            print(f"[✗] {p}")
    else:
        print("[✓] Nenhum problema óbvio detectado")
    
    print("\n[!] Para mais detalhes, verifique o arquivo: steam_audit.log")


def validar_isolamento_usuario(email1: str, email2: str) -> None:
    """Valida que bibliotecas de usuários diferentes não se misturam"""
    
    print("\n" + "="*80)
    print("VALIDAÇÃO: Isolamento de Usuários")
    print("="*80)
    
    if email1 not in USUARIOS_DB:
        print(f"[✗] Usuário 1 não encontrado: {email1}")
        return
    
    if email2 not in USUARIOS_DB:
        print(f"[✗] Usuário 2 não encontrado: {email2}")
        return
    
    biblioteca1 = GerenciadorBiblioteca.obter_biblioteca(email1)
    biblioteca2 = GerenciadorBiblioteca.obter_biblioteca(email2)
    
    appids1 = {item.jogo_id for item in biblioteca1}
    appids2 = {item.jogo_id for item in biblioteca2}
    
    print(f"\nUsuário 1 ({email1}):")
    print(f"  Jogos: {len(biblioteca1)}")
    
    print(f"\nUsuário 2 ({email2}):")
    print(f"  Jogos: {len(biblioteca2)}")
    
    # Detecta overlaps
    sobreposicao = appids1 & appids2
    
    if sobreposicao:
        print(f"\n[✗] ALERTA: Sobreposição detectada!")
        print(f"    Jogos comuns (possível mistura): {len(sobreposicao)}")
        for appid in list(sobreposicao)[:5]:
            print(f"      - AppID {appid}")
        if len(sobreposicao) > 5:
            print(f"      ... e mais {len(sobreposicao) - 5}")
    else:
        print(f"\n[✓] OK: Bibliotecas isoladas corretamente")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python audit_steam_completo.py <steam_id64_ou_url>")
        print("\nExemplos:")
        print("  python audit_steam_completo.py 76561198123456789")
        print("  python audit_steam_completo.py https://steamcommunity.com/profiles/76561198123456789")
        print("  python audit_steam_completo.py https://steamcommunity.com/id/seu-nick")
        sys.exit(1)
    
    steam_input = sys.argv[1]
    auditar_scraping_steam(steam_input)
