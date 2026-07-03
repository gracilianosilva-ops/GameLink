from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from modelos.usuario import Usuario, Admin, USUARIOS_DB
from modelos.jogo import Jogo, Categoria, JOGOS_DB
from modelos.posts import Post, Comentario, POSTS_DB, COMENTARIOS_POSTS_DB
from modelos.amigos_biblioteca import (
    GerenciadorAmigos, GerenciadorBiblioteca, GerenciadorReviews,
    GerenciadorNotificacoes, GerenciadorMensagens,
    AMIZADES_DB, BIBLIOTECA_DB, REVIEWS_DB, REVIEW_COMENTARIOS_DB, NOTIFICACOES_DB, MENSAGENS_DB
)
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from time import time
from functools import lru_cache
from html.parser import HTMLParser
from html import escape, unescape
from email.message import EmailMessage
import smtplib
from urllib.parse import quote, urlparse, urlencode
from urllib.request import Request, urlopen
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import secrets
from excecao import AutenticacaoError
from database import (
    init_db,
    get_connection,
    carregar_estado_persistido,
    persistir_usuario,
    persistir_categoria,
    persistir_jogo,
    remover_jogo,
    persistir_post,
    persistir_comentario_post,
    marcar_post_visivel,
    marcar_comentario_post_visivel,
    persistir_post_like,
    persistir_amizade,
    remover_amizade,
    persistir_biblioteca_item,
    remover_biblioteca_item,
    persistir_review,
    persistir_review_comentario,
    marcar_review_visivel,
    marcar_review_comentario_visivel,
    persistir_notificacao,
    marcar_notificacao_lida,
    persistir_mensagem,
)

app = Flask(__name__)
app.secret_key = "super_secret_key_gamelink"

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 5000
BASE_URL = f"http://{LOCAL_HOST}:{LOCAL_PORT}"
app.config["SERVER_NAME"] = f"{LOCAL_HOST}:{LOCAL_PORT}"

# Rastreamento de estado real (não cache - validado sempre)
_hydra_state_real = {
    'hydra_ativo': False,
    'jogo_atual': '',
    'ultima_validacao': 0,
    'processos_detectados': [],
}

# Bloqueio para evitar race conditions
import threading
_hydra_state_lock = threading.Lock()


def _carregar_env_local() -> None:
    caminho_env = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(caminho_env):
        return

    with open(caminho_env, 'r', encoding='utf-8') as arquivo:
        for linha in arquivo:
            texto = linha.strip()
            if not texto or texto.startswith('#') or '=' not in texto:
                continue
            chave, valor = texto.split('=', 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor


_carregar_env_local()

# Inicializa o banco de dados SQLite se ainda não existir
init_db()


def _normalizar_email(email: str) -> str:
    return (email or '').strip().lower()


def _gerar_codigo_verificacao() -> str:
    return f'{secrets.randbelow(1000000):06d}'


def _enviar_codigo_verificacao_email(destinatario: str, codigo: str, nome: str) -> bool:
    host = os.environ.get('MAIL_HOST', '').strip()
    usuario = os.environ.get('MAIL_USERNAME', '').strip()
    senha = os.environ.get('MAIL_PASSWORD', '').strip()
    remetente = os.environ.get('MAIL_FROM', usuario or 'noreply@gamelink.local').strip()
    porta = int(os.environ.get('MAIL_PORT', '587'))
    usar_tls = os.environ.get('MAIL_USE_TLS', '1').strip().lower() not in {'0', 'false', 'nao', 'no'}
    usar_ssl = os.environ.get('MAIL_USE_SSL', '0').strip().lower() in {'1', 'true', 'sim', 'yes'}

    if not host:
        print(f'[GameLink] Verificação local para {destinatario}: {codigo}')
        return False

    mensagem = EmailMessage()
    mensagem['Subject'] = 'Seu código de verificação GameLink'
    mensagem['From'] = remetente
    mensagem['To'] = destinatario
    mensagem.set_content(
        f'''Olá, {nome}.

Seu código de verificação do GameLink é: {codigo}

Esse código expira em 10 minutos.
Se você não solicitou este cadastro, ignore esta mensagem.
'''
    )

    if usar_ssl:
        servidor = smtplib.SMTP_SSL(host, porta, timeout=15)
    else:
        servidor = smtplib.SMTP(host, porta, timeout=15)

    with servidor as smtp:
        smtp.ehlo()
        if usar_tls and not usar_ssl:
            smtp.starttls()
            smtp.ehlo()
        if usuario:
            smtp.login(usuario, senha)
        smtp.send_message(mensagem)
    return True


def _cadastro_pendente_valido() -> dict | None:
    pendente = session.get('cadastro_pendente')
    if not pendente:
        return None
    if pendente.get('expira_em', 0) < time():
        session.pop('cadastro_pendente', None)
        return None
    return pendente


def _carregar_usuarios_do_banco() -> None:
    USUARIOS_DB.clear()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
         SELECT id, nome, email, password, idade, gosto_jogos, telefone,
             steam_id64, steam_api_key, steam_online, steam_current_game, 
             steam_current_game_appid, steam_playtime_minutes, steam_last_update,
             hydra_account_email, hydra_usuario, hydra_pin, hydra_token, hydra_current_game, hydra_last_update, foto_perfil, is_admin
        FROM usuarios
        ORDER BY id ASC
        '''
    )
    for row in cursor.fetchall():
        user = Admin(row['id'], row['nome'], row['email'], row['password']) if row['is_admin'] else Usuario(row['id'], row['nome'], row['email'], row['password'])
        user.idade = row['idade']
        user.gosto_jogos = row['gosto_jogos'] or ''
        user.telefone = row['telefone'] or ''
        user.steam_id64 = row['steam_id64'] or ''
        user.steam_api_key = row['steam_api_key'] or ''
        user.steam_online = bool(row['steam_online']) if row['steam_online'] is not None else False
        user.steam_current_game = row['steam_current_game'] or ''
        user.steam_current_game_appid = row['steam_current_game_appid']
        user.steam_playtime_minutes = row['steam_playtime_minutes'] or 0
        user.steam_last_update = row['steam_last_update'] or None
        user.hydra_account_email = row['hydra_account_email'] or ''
        user.hydra_usuario = row['hydra_usuario'] or ''
        user.hydra_pin = row['hydra_pin'] or ''
        user.hydra_token = row['hydra_token'] or ''
        user.hydra_current_game = row['hydra_current_game'] or ''
        user.hydra_last_update = row['hydra_last_update'] or None
        user.foto_perfil = row['foto_perfil'] or ''
        USUARIOS_DB[user.email.lower()] = user
    conn.close()


def _salvar_usuario_no_banco(user) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO usuarios (
            nome, email, password, idade, gosto_jogos, telefone,
            steam_id64, steam_api_key, steam_online, steam_current_game,
            steam_current_game_appid, steam_playtime_minutes, steam_last_update,
            hydra_account_email, hydra_usuario, hydra_pin, hydra_token, hydra_current_game, hydra_last_update, foto_perfil, is_admin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            nome=excluded.nome,
            password=excluded.password,
            idade=excluded.idade,
            gosto_jogos=excluded.gosto_jogos,
            telefone=excluded.telefone,
            steam_id64=excluded.steam_id64,
            steam_api_key=excluded.steam_api_key,
            steam_online=excluded.steam_online,
            steam_current_game=excluded.steam_current_game,
            steam_current_game_appid=excluded.steam_current_game_appid,
            steam_playtime_minutes=excluded.steam_playtime_minutes,
            steam_last_update=excluded.steam_last_update,
            hydra_account_email=excluded.hydra_account_email,
            hydra_usuario=excluded.hydra_usuario,
            hydra_pin=excluded.hydra_pin,
            hydra_token=excluded.hydra_token,
            hydra_current_game=excluded.hydra_current_game,
            hydra_last_update=excluded.hydra_last_update,
            foto_perfil=excluded.foto_perfil,
            is_admin=excluded.is_admin
        ''',
        (
            user.nome,
            user.email,
            user._Usuario__password if hasattr(user, '_Usuario__password') else '',
            user.idade,
            user.gosto_jogos,
            user.telefone,
            user.steam_id64,
            user.steam_api_key,
            1 if user.steam_online else 0,
            user.steam_current_game,
            user.steam_current_game_appid,
            user.steam_playtime_minutes,
            user.steam_last_update,
            user.hydra_account_email,
            user.hydra_usuario,
            user.hydra_pin,
            user.hydra_token,
            user.hydra_current_game,
            user.hydra_last_update,
            getattr(user, 'foto_perfil', ''),
            1 if isinstance(user, Admin) else 0,
        )
    )
    conn.commit()
    conn.close()


def _garantir_admin_no_banco() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM usuarios WHERE email = ?', ('admin@gamelink.com',))
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO usuarios (id, nome, email, password, is_admin) VALUES (?, ?, ?, ?, ?)',
            (1, 'Caxa', 'admin@gamelink.com', 'admin123', 1)
        )
        conn.commit()
    conn.close()


_garantir_admin_no_banco()
_carregar_usuarios_do_banco()

# Configuração de uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

DEFAULT_HYDRA_API_BASE_URL = (
    os.environ.get('HYDRA_API_BASE_URL', 'https://hydra-api-us-east-1.losbroxas.org')
    .strip()
    .rstrip('/')
)
HYDRA_APPDATA_DIR = os.path.join(os.environ.get('APPDATA', ''), 'hydralauncher')

# Controle de presença online em memória
ONLINE_USERS = set()
CALL_PRESENCE = {}

CALL_PRESENCE_TTL = 35

def esta_online(email: str) -> bool:
    normalized = _normalizar_email(email)
    user = USUARIOS_DB.get(normalized)
    if user:
        if user.hydra_current_game:
            return True
        current_user_email = _normalizar_email(session.get('user_email', ''))
        if normalized == current_user_email and _hydra_local_ativo_real():
            return True
        if user.steam_online:
            return True
    return normalized in ONLINE_USERS or _presenca_call_ativa(normalized)


def _presenca_call_ativa(email: str) -> bool:
    dados = CALL_PRESENCE.get(email)
    if not dados:
        return False
    return (time() - dados.get('last_seen', 0)) <= CALL_PRESENCE_TTL


def _registrar_presenca_call(email: str, room_slug: str) -> None:
    agora = time()
    dados_atuais = CALL_PRESENCE.get(email, {})
    CALL_PRESENCE[email] = {
        'room_slug': room_slug,
        'last_seen': agora,
        'joined_at': dados_atuais.get('joined_at', agora),
    }


def _remover_presenca_call(email: str) -> None:
    CALL_PRESENCE.pop(email, None)


def _limpar_presencas_call() -> None:
    expiradas = [email for email, dados in CALL_PRESENCE.items() if (time() - dados.get('last_seen', 0)) > CALL_PRESENCE_TTL]
    for email in expiradas:
        CALL_PRESENCE.pop(email, None)
        user = USUARIOS_DB.get(email)
        if user:
            user.discord_online = False


def _obter_participantes_call_ativos(room_slug: str) -> list:
    _limpar_presencas_call()
    participantes = []
    for email, dados in CALL_PRESENCE.items():
        if dados.get('room_slug') != room_slug:
            continue
        usuario = USUARIOS_DB.get(email)
        if not usuario:
            continue
        participantes.append({
            'email': usuario.email,
            'nome': usuario.nome,
            'joined_at': dados.get('joined_at', dados.get('last_seen', time())),
            'last_seen': dados.get('last_seen', time()),
        })
    participantes.sort(key=lambda item: item['nome'].lower())
    return participantes


def _formatar_tempo_decorrido(segundos: float) -> str:
    total = max(0, int(segundos))
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    return f'{horas:02d}:{minutos:02d}:{segundos:02d}'


def _serializar_status_call(room_slug: str) -> dict:
    participantes_ativos = _obter_participantes_call_ativos(room_slug)
    call_iniciada_em = min((item['joined_at'] for item in participantes_ativos), default=time())
    return {
        'participantes_ativos': participantes_ativos,
        'quantidade': len(participantes_ativos),
        'tempo_decorrido': _formatar_tempo_decorrido(time() - call_iniciada_em),
        'call_iniciada_em': call_iniciada_em,
    }

@app.context_processor
def inject_status_helpers():
    _limpar_presencas_call()
    return {'esta_online': esta_online, 'em_call': _presenca_call_ativa}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _capa_fallback(titulo: str) -> str:
        titulo_limpo = escape((titulo or 'Jogo')[:30])
        svg = f'''
        <svg xmlns="http://www.w3.org/2000/svg" width="600" height="900" viewBox="0 0 600 900">
            <defs>
                <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stop-color="#0f172a"/>
                    <stop offset="100%" stop-color="#1e293b"/>
                </linearGradient>
                <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.95"/>
                    <stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.15"/>
                </linearGradient>
            </defs>
            <rect width="600" height="900" rx="36" fill="url(#bg)"/>
            <circle cx="120" cy="120" r="110" fill="#38bdf8" fill-opacity="0.08"/>
            <circle cx="500" cy="790" r="180" fill="#0ea5e9" fill-opacity="0.08"/>
            <rect x="58" y="706" width="484" height="8" rx="4" fill="url(#accent)"/>
            <text x="300" y="418" fill="#7dd3fc" font-family="Arial, Helvetica, sans-serif" font-size="40" font-weight="700" text-anchor="middle">Capa não disponível</text>
            <text x="300" y="474" fill="#e2e8f0" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="600" text-anchor="middle">{titulo_limpo}</text>
        </svg>
        '''.strip()
        return 'data:image/svg+xml;charset=UTF-8,' + quote(svg)


def _normalizar_busca(texto: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (texto or '').lower()).strip()


def _extrair_ano_texto(titulo: str) -> int | None:
    correspondencia = re.search(r'\b(19\d{2}|20\d{2})\b', titulo or '')
    if not correspondencia:
        return None
    ano = int(correspondencia.group(1))
    return ano if 1950 <= ano <= 2035 else None


def _titulo_sem_ano(titulo: str) -> str:
    texto = re.sub(r'\b(19\d{2}|20\d{2})\b', ' ', titulo or '')
    return _normalizar_busca(texto)


RAWG_SLUGS_FIXOS = {
    ('the witcher 3', None): 'the-witcher-3-wild-hunt',
    ('the witcher 3 wild hunt', None): 'the-witcher-3-wild-hunt',
    ('elden ring', None): 'elden-ring',
    ('gta v', None): 'grand-theft-auto-v',
    ('grand theft auto v', None): 'grand-theft-auto-v',
    ('god of war', 2005): 'god-of-war',
    ('god of war', 2018): 'god-of-war-2',
    ('god of war ragnarok', 2022): 'god-of-war-ragnarok',
}


def _buscar_html_com_user_agent(url: str, timeout: int = 10) -> str:
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        },
    )
    with urlopen(request, timeout=timeout) as resposta:
        return resposta.read().decode('utf-8', errors='replace')


def _obter_slug_rawg(titulo: str, ano: int | None = None) -> str | None:
    ano_detectado = ano if ano is not None else _extrair_ano_texto(titulo)
    titulo_base = _titulo_sem_ano(titulo)

    slug_fixo = RAWG_SLUGS_FIXOS.get((titulo_base, ano_detectado)) or RAWG_SLUGS_FIXOS.get((titulo_base, None))
    if slug_fixo:
        return slug_fixo

    html = _buscar_html_com_user_agent(f'https://rawg.io/games?search={quote(titulo_base or titulo)}', timeout=10)
    candidatos = re.findall(r'<a class="game-card-medium__info__name" href="/games/([^"]+)">([^<]+)', html, re.I)
    if not candidatos:
        return None

    busca_normalizada = titulo_base or _normalizar_busca(titulo)
    melhor_slug = None
    melhor_pontuacao = 0.0
    for slug, nome in candidatos:
        nome_normalizado = _normalizar_busca(nome)
        pontuacao = SequenceMatcher(None, busca_normalizada, nome_normalizado).ratio()
        if ano_detectado and re.search(rf'\b{ano_detectado}\b', nome):
            pontuacao += 0.25
        if busca_normalizada and nome_normalizado == busca_normalizada:
            pontuacao += 0.4
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_slug = slug

    if melhor_pontuacao < 0.62:
        return None

    return melhor_slug


def _obter_capa_rawg(titulo: str, ano: int | None = None) -> str | None:
    slug = _obter_slug_rawg(titulo, ano)
    if not slug:
        return None

    html = _buscar_html_com_user_agent(f'https://rawg.io/games/{slug}', timeout=10)
    correspondencia = re.search(r'property="og:image" content="([^"]+)"', html, re.I)
    if correspondencia:
        return correspondencia.group(1)

    return None


def _capa_steam_jogo(appid: int) -> str:
    if not appid:
        return ''
    return f'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg'


def _capa_para_jogo_catalogo(jogo, usadas: set[str]) -> str:
    genero = (getattr(jogo, 'genero', '') or '').strip().lower()
    desenvolvedora = (getattr(jogo, 'desenvolvedora', '') or '').strip().lower()
    if genero == 'steam' or desenvolvedora == 'steam':
        capa = _capa_steam_jogo(int(getattr(jogo, 'id', 0) or 0))
        if capa:
            usadas.add(capa)
            return capa

    return _capa_unica_para_lista(getattr(jogo, 'titulo', ''), getattr(jogo, 'ano', None), usadas)


@lru_cache(maxsize=256)
def obter_capa_jogo(titulo: str, ano: int | None = None) -> str:
    if not titulo:
        return _capa_fallback('Jogo')

    try:
        capa_rawg = _obter_capa_rawg(titulo, ano)
        if capa_rawg:
            return capa_rawg
    except Exception:
        pass

    return _capa_fallback(titulo)


def _capa_unica_para_lista(titulo: str, ano: int | None, usadas: set[str]) -> str:
    capa = obter_capa_jogo(titulo, ano)
    if capa in usadas:
        capa = _capa_fallback(titulo)
    usadas.add(capa)
    return capa


def _steam_api_key_usuario(user) -> str:
    return (getattr(user, 'steam_api_key', '') or os.environ.get('STEAM_API_KEY') or '').strip()


def _steam_id_ou_vanity_usuario(user) -> str:
    return (getattr(user, 'steam_id64', '') or '').strip()


def _hydra_fetch_json(url: str, extra_headers: dict | None = None) -> dict | list:
    headers = {
        'User-Agent': 'GameLink/1.0',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    }
    if extra_headers:
        headers.update(extra_headers)

    request = Request(
        url,
        headers=headers,
    )
    with urlopen(request, timeout=8) as resposta:
        return json.loads(resposta.read().decode('utf-8', errors='replace'))


def _hydra_token_local_detectado() -> str:
    tokens = _hydra_tokens_locais_detectados()
    return tokens[0] if tokens else ''


def _hydra_tokens_locais_detectados() -> list[str]:
    if not HYDRA_APPDATA_DIR or not os.path.isdir(HYDRA_APPDATA_DIR):
        return []

    candidatos = [
        os.path.join(HYDRA_APPDATA_DIR, 'hydra-db', '000005.ldb'),
        os.path.join(HYDRA_APPDATA_DIR, 'hydra-db', '000006.log'),
        os.path.join(HYDRA_APPDATA_DIR, 'logs', 'network.txt'),
        os.path.join(HYDRA_APPDATA_DIR, 'logs', 'network.txt'),
        os.path.join(HYDRA_APPDATA_DIR, 'logs', 'info.txt'),
        os.path.join(HYDRA_APPDATA_DIR, 'logs', 'logs.txt'),
    ]

    tokens_encontrados = []

    for caminho in candidatos:
        if not os.path.isfile(caminho):
            continue

        try:
            with open(caminho, 'r', encoding='utf-8', errors='replace') as arquivo:
                conteudo = arquivo.read()
        except OSError:
            continue

        padroes = (
            r'"accessToken"\s*:\s*"([^"]+)"',
            r'"workwondersJwt"\s*:\s*"([^"]+)"',
            r'"token"\s*:\s*"([^"]+)"',
            r"workwondersJwt:\s*'([^']+)'",
            r"token:\s*'([^']+)'",
        )

        for padrao in padroes:
            for token in re.findall(padrao, conteudo):
                token = token.strip()
                if token and token not in tokens_encontrados:
                    tokens_encontrados.append(token)

        for token in re.findall(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", conteudo):
            token = token.strip()
            if token and token not in tokens_encontrados:
                tokens_encontrados.append(token)

    return tokens_encontrados


def _hydra_cache_local_jogos() -> tuple[list[dict], str]:
    caminho_log = os.path.join(HYDRA_APPDATA_DIR, 'logs', 'network.txt')
    if not os.path.isfile(caminho_log):
        return [], ''

    try:
        with open(caminho_log, 'r', encoding='utf-8', errors='replace') as arquivo:
            conteudo = arquivo.read()
    except OSError:
        return [], ''

    display_name = ''
    match_display_name = re.search(r"displayName:\s*'([^']+)'", conteudo)
    if match_display_name:
        display_name = match_display_name.group(1).strip()

    jogos = []
    padrao_jogo = re.compile(
        r"objectId:\s*'(?P<objectId>[^']+)'.*?shop:\s*'(?P<shop>[^']+)'.*?title:\s*'(?P<title>[^']+)'.*?coverImageUrl:\s*'(?P<coverImageUrl>[^']*)'.*?playTimeInSeconds:\s*(?P<playTimeInSeconds>\d+).*?achievementCount:\s*(?P<achievementCount>\d+).*?unlockedAchievementCount:\s*(?P<unlockedAchievementCount>\d+)",
        re.S,
    )

    for match in padrao_jogo.finditer(conteudo):
        jogos.append({
            'objectId': match.group('objectId').strip(),
            'shop': match.group('shop').strip(),
            'title': match.group('title').strip(),
            'cover_url': match.group('coverImageUrl').strip(),
            'playTimeInSeconds': int(match.group('playTimeInSeconds') or 0),
            'isPinned': False,
            'isFavorite': False,
            'achievements_unlocked': int(match.group('unlockedAchievementCount') or 0),
            'achievements_total': int(match.group('achievementCount') or 0),
        })

    return jogos, display_name


def _hydra_get_running_processes() -> set[str]:
    """Obtém lista de processos REAIS em execução no Windows (SEM CACHE).
    
    Esta função SEMPRE consulta o Windows para obter estado real.
    Nunca retorna dados em cache.
    
    Returns:
        Set com nomes de executáveis em minúsculas
    """
    try:
        # Tasklist rápido - SEM CACHE
        resultado = subprocess.run(
            ['tasklist'],
            capture_output=True,
            text=True,
            timeout=2.0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if resultado.returncode != 0:
            return set()
        
        processos = set()
        for linha in resultado.stdout.split('\n'):
            linha = linha.strip().lower()
            if linha and '.exe' in linha:
                partes = linha.split()
                if partes:
                    processos.add(partes[0])
        
        return processos
    except subprocess.TimeoutExpired:
        print('[Hydra REAL-STATE] Timeout ao listar processos')
        return set()
    except Exception as e:
        print(f'[Hydra REAL-STATE] Erro ao listar processos: {e}')
        return set()


def _hydra_obter_whitelist_executaveis() -> set[str]:
    """Extrai executáveis REAIS de jogos instalados.
    
    ESTRATÉGIA DEFINITIVA:
    1. Lê da pasta de jogos do Hydra (se existir)
    2. Adiciona executáveis da biblioteca local (BIBLIOTECA_DB)
    3. NUNCA retorna None - sempre retorna um set (vazio se necessário)
    4. Rejeita ABSOLUTAMENTE tudo se não tiver confirmação de jogo
    
    Returns:
        Set com executáveis em minúsculas (.exe incluído)
        Vazio se nenhum jogo for encontrado (modo SUPER SEGURO)
    """
    whitelist = set()
    
    # ESTRATÉGIA 1: Ler da pasta de jogos do Hydra
    try:
        games_dir = os.path.join(HYDRA_APPDATA_DIR, 'games')
        if os.path.isdir(games_dir):
            print(f'[Hydra WHITELIST] Lendo pasta de jogos: {games_dir}')
            for pasta_jogo in os.listdir(games_dir):
                caminho_jogo = os.path.join(games_dir, pasta_jogo)
                if os.path.isdir(caminho_jogo):
                    meta_file = os.path.join(caminho_jogo, 'metadata.json')
                    if os.path.isfile(meta_file):
                        try:
                            with open(meta_file, 'r', encoding='utf-8', errors='replace') as f:
                                meta = json.load(f)
                                exe = (meta.get('executable') or 
                                      meta.get('executablePath') or 
                                      meta.get('launchPath') or '').lower().strip()
                                
                                if exe and exe.endswith('.exe'):
                                    whitelist.add(exe)
                                    game_title = meta.get('title', pasta_jogo)
                                    print(f'[Hydra WHITELIST] OK Jogo Hydra: {game_title} -> {exe}')
                        except Exception as e:
                            print(f'[Hydra WHITELIST] Erro ao ler {meta_file}: {e}')
    except Exception as e:
        print(f'[Hydra WHITELIST] Erro ao ler pasta de jogos: {e}')
    
    # ESTRATÉGIA 2: Adiciona executáveis da biblioteca local do GameLink
    try:
        if BIBLIOTECA_DB and isinstance(BIBLIOTECA_DB, dict):
            print(f'[Hydra WHITELIST] Lendo biblioteca local ({len(BIBLIOTECA_DB)} itens)')
            for game_id, item in BIBLIOTECA_DB.items():
                try:
                    exe = None
                    
                    if hasattr(item, 'executavel'):
                        exe = item.executavel
                    elif hasattr(item, 'executable'):
                        exe = item.executable
                    elif hasattr(item, 'launch_path'):
                        exe = item.launch_path
                    elif isinstance(item, dict):
                        exe = item.get('executavel') or item.get('executable')
                    
                    if exe:
                        exe = str(exe).lower().strip()
                        if '\\' in exe or '/' in exe:
                            exe = os.path.basename(exe)
                        
                        if exe and exe.endswith('.exe'):
                            whitelist.add(exe)
                            game_title = getattr(item, 'titulo', getattr(item, 'title', game_id))
                            print(f'[Hydra WHITELIST] OK Jogo GameLink: {game_title} -> {exe}')
                except Exception as e:
                    print(f'[Hydra WHITELIST] Erro ao processar item {game_id}: {e}')
    except Exception as e:
        print(f'[Hydra WHITELIST] Erro ao ler BIBLIOTECA_DB: {e}')
    
    if not whitelist:
        print('[Hydra WHITELIST] AVISO: Nenhum jogo encontrado - modo SUPER SEGURO')
    else:
        print(f'[Hydra WHITELIST] OK Total de executaveis validos: {len(whitelist)}')
        for exe in sorted(whitelist)[:3]:
            print(f'[Hydra WHITELIST]    - {exe}')
    
    return whitelist


# BLACKLIST ABRANGENTE: Todos os processos que NÃO são jogos
# Inclui: Sistema, Drivers, Antivírus, Navegadores, Messaging, Dev Tools
_BLACKLIST_PROCESSOS_SISTEMA = {
    # Sistema Windows
    'system.exe', 'idle.exe', 'svchost.exe', 'services.exe', 'lsass.exe',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe', 'logonui.exe',
    'userinit.exe', 'dwm.exe', 'explorer.exe', 'taskhostw.exe', 'taskhost.exe',
    'conhost.exe', 'spoolsv.exe', 'rundll32.exe', 'regsvcs.exe', 'regasm.exe',
    'msiexec.exe', 'wisptis.exe',
    
    # Gerenciador de tarefas e ferramentas
    'taskmgr.exe', 'taskmgrexe', 'taskmgre.exe', 'devmgmt.exe', 'diskmgmt.exe',
    'compmgmt.exe', 'eventvwr.exe', 'perfmon.exe', 'resmon.exe', 'werfault.exe',
    'drwtsn32.exe', 'verclsid.exe', 'wudfhost.exe',
    
    # Antivírus e Segurança
    'msseces.exe', 'avp.exe', 'avpui.exe', 'avgui.exe', 'afwserv.exe',
    'fshoster32.exe', 'mcshield.exe', 'mctray.exe', 'isafe.exe',
    'ntssrvcs.exe', 'symproxysvc.exe', 'zlsvc.exe', 'zlclient.exe',
    'emsw.exe', 'shstat.exe', 'swdoctor.exe', 'swagent.exe',
    
    # Navegadores
    'chrome.exe', 'firefox.exe', 'msedge.exe', 'iexplore.exe', 'opera.exe',
    'safari.exe', 'vivaldi.exe', 'brave.exe', 'waterfox.exe',
    
    # Comunicação
    'discord.exe', 'telegram.exe', 'whatsapp.exe', 'skype.exe', 'teams.exe',
    'slack.exe', 'thunderbird.exe', 'outlook.exe',
    
    # Produtividade
    'winword.exe', 'excel.exe', 'powerpnt.exe', 'onenote.exe', 'access.exe',
    'code.exe', 'vim.exe', 'notepad.exe', 'notepad++.exe',
    
    # Cloud/Sync
    'dropbox.exe', 'googledrivesync.exe', 'onedrive.exe', 'sync.exe',
    
    # Serviços
    'python.exe', 'pythonw.exe', 'node.exe', 'npm.exe', 'java.exe', 'javaw.exe',
    'ruby.exe', 'perl.exe', 'php.exe', 'flask.exe', 'hydra.exe',
    
    # Sistema/Drivers
    'svchost.exe', 'rundll32.exe', 'ctfmon.exe', 'dllhost.exe',
    'nvcontainer.exe', 'nvdisplay.exe', 'amd radeon settings.exe',
    'igfxem.exe', 'igfxtray.exe', 'hkcmd.exe',
    
    # Audio/Vídeo
    'audiodg.exe', 'snd.exe', 'wmplayer.exe', 'vlc.exe', 'mpv.exe',
    'mpc-hc.exe', 'potplayer.exe',
    
    # Utilitários
    '7zfm.exe', 'winrar.exe', 'peazip.exe', 'everything.exe',
    'totalcmd.exe', 'powertoys.exe', 'putty.exe', 'winscp.exe',
    
    # Virtualização
    'vmwareplayer.exe', 'vmware.exe', 'vboxheadless.exe', 'virtualbox.exe',
    
    # Game Launchers/Platform Utilities (não são jogos)
    'steam.exe', 'epicgameslauncher.exe', 'launcher.exe', 'egl-launcher.exe',
    'gog galaxy.exe', 'bethesdanet.exe', 'uplay.exe', 'ubisoft.exe',
    'playnite.exe', 'lutris.exe', 'wineserver.exe', 'proton.exe',
    'steamruntime.exe', 'steamwebhelper.exe', 'steamclient.exe',
    
    # Windows Store e Serviços
    'wsappx.exe', 'w10updateassistant.exe', 'windowsupdater.exe',
    'trustedinstaller.exe', 'tiworker.exe', 'searchindexer.exe',
    'searchfilterhost.exe', 'searchprotocolhost.exe', 'background transfer service.exe',
    
    # Drivers/Kernel
    'ntdll.exe', 'kernel32.exe', 'dxgi.dll', 'd3d11.dll', 'dxdiag.exe',
    'dxdiagn.dll', 'wddm1_0.exe'
}


def _hydra_detect_running_game_real() -> str:
    """Detecta jogo em execução NO HYDRA com validacao RIGOROSA (SEM CACHE).
    
    ARQUITETURA DEFINITIVA:
    1. Obtém whitelist de jogos REAIS instalados
    2. Obtém processos em execução
    3. REJEITA TUDO na BLACKLIST de sistema
    4. VALIDA contra a WHITELIST
    5. SO retorna se confirmado como jogo
    
    Returns:
        Nome do jogo ou string vazia ('')
    """
    # PASSO 1: Obter whitelist de jogos REAIS
    whitelist = _hydra_obter_whitelist_executaveis()
    
    # Se nao ha nenhum jogo instalado, nada a fazer
    if not whitelist:
        print('[Hydra DETECT] Info: Nenhum jogo instalado detectado')
        return ''
    
    # PASSO 2: Obter processos em execucao
    processos_ativos = _hydra_get_running_processes()
    
    if not processos_ativos:
        print('[Hydra DETECT] Info: Nenhum processo ativo')
        return ''
    
    print(f'[Hydra DETECT] Processos ativos: {len(processos_ativos)}')
    print(f'[Hydra DETECT] Whitelist de jogos: {len(whitelist)} itens')
    
    # PASSO 3: Filtrar BLACKLIST (primeira linha de defesa)
    print(f'[Hydra DETECT] Filtrando blacklist...')
    processos_candidatos = set()
    processos_rejeitados = set()
    
    for proc in processos_ativos:
        if proc in _BLACKLIST_PROCESSOS_SISTEMA:
            processos_rejeitados.add(proc)
            continue
        processos_candidatos.add(proc)
    
    if processos_rejeitados:
        print(f'[Hydra DETECT] Rejeitados pela blacklist: {len(processos_rejeitados)}')
        for proc in sorted(processos_rejeitados)[:3]:
            print(f'[Hydra DETECT]    - {proc}')
    
    if not processos_candidatos:
        print(f'[Hydra DETECT] Nenhum candidato apos blacklist')
        return ''
    
    print(f'[Hydra DETECT] Candidatos apos blacklist: {len(processos_candidatos)}')
    
    # PASSO 4: Validar contra WHITELIST
    print(f'[Hydra DETECT] Validando contra whitelist...')
    processos_validos = [p for p in processos_candidatos if p in whitelist]
    
    if processos_validos:
        jogo_exe = processos_validos[0]
        jogo_nome = jogo_exe.replace('.exe', '').title()
        print(f'[Hydra DETECT] OK JOGO DETECTADO: "{jogo_nome}" (exe: {jogo_exe})')
        return jogo_nome
    
    print(f'[Hydra DETECT] Nenhum processo corresponde a whitelist')
    return ''




def _hydra_local_ativo_real() -> bool:
    """Verifica se Hydra REALMENTE está em execução (SEM CACHE).
    
    Sempre consulta o Windows para estado REAL.
    
    Returns:
        True se Hydra está rodando, False caso contrário
    """
    processos = _hydra_get_running_processes()
    
    # Procura por qualquer processo contendo 'hydra'
    for proc in processos:
        if 'hydra' in proc.lower():
            print(f'[Hydra REAL] Hydra detectado: {proc}')
            return True
    
    print(f'[Hydra REAL] Hydra NÃO está rodando')
    return False


def _hydra_get_full_state_real() -> dict:
    """Retorna ESTADO REAL COMPLETO do Hydra (SEM CACHE).
    
    Este é o ponto central de verdade para o estado do Hydra.
    SEMPRE valida contra o sistema real.
    NUNCA usa dados armazenados.
    
    Returns:
        Dict com {'hydra_ativo': bool, 'jogo': str, 'usuario': str}
    """
    estado = {
        'hydra_ativo': _hydra_local_ativo_real(),
        'jogo': '',
        'usuario': ''
    }
    
    # Se Hydra não está ativo, não precisa procurar jogo
    if not estado['hydra_ativo']:
        return estado
    
    # Hydra está ativo, procura por jogo
    estado['jogo'] = _hydra_detect_running_game_real()
    
    # Tenta obter nome de usuário
    try:
        config_path = os.path.join(HYDRA_APPDATA_DIR, 'config.json')
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                config = json.load(f)
                estado['usuario'] = config.get('userDetails', {}).get('username', '').strip() or config.get('username', '').strip()
    except Exception:
        pass  # Silencioso
    
    return estado


def _hydra_sincronizar_estado_real(user) -> None:
    """Sincroniza estado do usuário com ESTADO REAL do Hydra (SEM CACHE).
    
    SEMPRE valida contra o sistema real.
    Limpa estado inconsistente.
    NUNCA confia em dados armazenados.
    
    Args:
        user: Usuario object
    """
    if not user:
        return
    
    # Valida estado REAL do sistema (SEMPRE!)
    estado_real = _hydra_get_full_state_real()
    agora = datetime.now().isoformat()
    
    print(f'[Hydra SYNC] {user.email}: Validando estado REAL')
    print(f'[Hydra SYNC]   Hydra ativo: {estado_real["hydra_ativo"]}')
    print(f'[Hydra SYNC]   Jogo real: "{estado_real["jogo"]}"')
    print(f'[Hydra SYNC]   Armazenado: "{user.hydra_current_game}"')
    
    # Caso 1: Hydra não está rodando
    if not estado_real['hydra_ativo']:
        if user.hydra_current_game:
            print(f'[Hydra SYNC] ❌ INCONSISTÊNCIA: Hydra FECHADO mas DB tem status')
            print(f'[Hydra SYNC] 🔧 CORRIGINDO: Limpando')
            user.hydra_current_game = ''
            user.hydra_last_update = agora
            _salvar_usuario_no_banco(user)
        return
    
    # Caso 2: Hydra ativo - verifica se jogo mudou
    if estado_real['jogo'] != user.hydra_current_game:
        if estado_real['jogo']:
            print(f'[Hydra SYNC] 🎮 JOGO INICIADO: "{estado_real["jogo"]}"')
        else:
            print(f'[Hydra SYNC] 🛑 JOGO FECHADO')
        
        user.hydra_current_game = estado_real['jogo']
        user.hydra_last_update = agora
        _salvar_usuario_no_banco(user)
        print(f'[Hydra SYNC] ✅ Atualizado')


# Manter para compatibilidade com código antigo
def _hydra_atualizar_status_local(user) -> None:
    """Compatibilidade - redireciona para nova função."""
    _hydra_sincronizar_estado_real(user)


def _hydra_email_conta_usuario(user) -> str:
    return (getattr(user, 'hydra_account_email', '') or '').strip()


def _hydra_usuario_usuario(user) -> str:
    return (getattr(user, 'hydra_usuario', '') or '').strip()


def _hydra_pin_usuario(user) -> str:
    return (getattr(user, 'hydra_pin', '') or '').strip()


def _hydra_token_usuario(user) -> str:
    return (getattr(user, 'hydra_token', '') or '').strip()


def _hydra_fetch_autenticado_json(base_url: str, caminho: str, token: str) -> dict | list:
    return _hydra_fetch_json(
        f'{base_url}{caminho}',
        {'Authorization': f'Bearer {token}'}
    )


def _hydra_ler_duracao_em_segundos(item: dict) -> int:
    for chave in (
        'playTimeInSeconds',
        'playTimeSeconds',
        'playtime_seconds',
        'timePlayedSeconds',
        'secondsPlayed',
        'durationSeconds',
    ):
        valor = item.get(chave)
        if valor not in (None, ''):
            try:
                return max(0, int(float(valor)))
            except (TypeError, ValueError):
                pass

    for chave in (
        'playtime_forever',
        'playTimeInMinutes',
        'playtimeMinutes',
        'timePlayedMinutes',
        'minutesPlayed',
        'durationMinutes',
    ):
        valor = item.get(chave)
        if valor not in (None, ''):
            try:
                return max(0, int(float(valor) * 60))
            except (TypeError, ValueError):
                pass

    return 0


def _hydra_ler_conquistas_item(item: dict) -> tuple[int, int]:
    conquistas = item.get('achievements') or item.get('achievement') or item.get('conquistas')
    desbloqueadas = 0
    total = 0

    if isinstance(conquistas, list):
        total = len(conquistas)
        desbloqueadas = sum(
            1
            for conquista in conquistas
            if isinstance(conquista, dict)
            and bool(
                conquista.get('unlocked')
                or conquista.get('earned')
                or conquista.get('completed')
                or conquista.get('active')
            )
        )
    elif isinstance(conquistas, dict):
        desbloqueadas = int(
            conquistas.get('unlocked')
            or conquistas.get('unlockedCount')
            or conquistas.get('earned')
            or conquistas.get('completed')
            or conquistas.get('progress')
            or 0
        )
        total = int(
            conquistas.get('total')
            or conquistas.get('count')
            or conquistas.get('achievementCount')
            or 0
        )
    else:
        desbloqueadas = int(
            item.get('achievementsUnlocked')
            or item.get('unlockedAchievements')
            or item.get('achievementUnlockedCount')
            or 0
        )
        total = int(
            item.get('achievementsTotal')
            or item.get('totalAchievements')
            or item.get('achievementTotalCount')
            or 0
        )

    if total == 0 and desbloqueadas > 0:
        total = desbloqueadas
    if total and desbloqueadas > total:
        desbloqueadas = total

    return max(0, desbloqueadas), max(0, total)


def _hydra_extrair_jogos_exportados(dados_exportados: dict | list) -> list[dict]:
    if isinstance(dados_exportados, list):
        itens = dados_exportados
    elif isinstance(dados_exportados, dict):
        itens = []
        for chave in ('library', 'games', 'items', 'pinnedGames', 'profileGames'):
            valor = dados_exportados.get(chave)
            if isinstance(valor, list):
                itens.extend(valor)

        if not itens:
            for chave in ('data', 'result', 'results'):
                valor = dados_exportados.get(chave)
                if isinstance(valor, list):
                    itens.extend(valor)
                elif isinstance(valor, dict):
                    for chave_interna in ('library', 'games', 'items', 'pinnedGames'):
                        valor_interno = valor.get(chave_interna)
                        if isinstance(valor_interno, list):
                            itens.extend(valor_interno)
    else:
        return []

    jogos = []
    for indice, item in enumerate(itens, start=1):
        if not isinstance(item, dict):
            continue

        titulo = (
            item.get('title')
            or item.get('name')
            or item.get('gameTitle')
            or item.get('gameName')
            or item.get('appName')
            or ''
        ).strip()
        if not titulo:
            continue

        codigo_origem = str(
            item.get('id')
            or item.get('gameId')
            or item.get('appid')
            or item.get('slug')
            or titulo
        ).strip().lower()
        play_seconds = _hydra_ler_duracao_em_segundos(item)
        conquistas_desbloqueadas, conquistas_total = _hydra_ler_conquistas_item(item)

        jogos.append({
            'titulo': titulo,
            'codigo_origem': codigo_origem or f'hydra-{indice}',
            'play_seconds': play_seconds,
            'conquistas_desbloqueadas': conquistas_desbloqueadas,
            'conquistas_total': conquistas_total,
        })

    return jogos


def _hydra_contexto_local(user) -> dict:
    jogos = []
    conquistas_desbloqueadas_total = 0
    conquistas_total = 0
    capas_usadas: set[str] = set()

    for item in GerenciadorBiblioteca.obter_biblioteca(user.email):
        if (getattr(item, 'origem', '') or '').lower() != 'hydra':
            continue

        jogo = JOGOS_DB.get(item.jogo_id)
        if not jogo:
            continue

        desbloqueadas = int(getattr(item, 'conquistas_desbloqueadas', 0) or 0)
        total_item = int(getattr(item, 'conquistas_total', 0) or 0)
        conquistas_desbloqueadas_total += desbloqueadas
        conquistas_total += total_item

        jogos.append({
            'appid': jogo.id,
            'name': jogo.titulo,
            'title': jogo.titulo,
            'playTimeInSeconds': int(getattr(item, 'tempo_jogado_horas', 0) or 0) * 3600,
            'shop': 'hydra',
            'cover_url': _capa_unica_para_lista(jogo.titulo, jogo.ano, capas_usadas),
            'achievements_unlocked': desbloqueadas,
            'achievements_total': total_item,
        })

    if not jogos:
        return {
            'configurado': False,
            'erro': 'Importe uma exportação local da Hydra para exibir sua biblioteca aqui.',
            'jogos': [],
            'jogos_totais': 0,
            'usuario': None,
            'perfil_url': None,
            'base_url': None,
            'email_conta': _hydra_email_conta_usuario(user),
            'hydra_usuario': _hydra_usuario_usuario(user),
            'hydra_pin': _hydra_pin_usuario(user),
            'origem': 'importacao_local',
        }

    return {
        'configurado': True,
        'erro': None,
        'jogos': jogos,
        'jogos_totais': len(jogos),
        'usuario': {'displayName': user.nome, 'email': user.email},
        'perfil_url': None,
        'base_url': None,
        'email_conta': _hydra_email_conta_usuario(user),
        'hydra_usuario': _hydra_usuario_usuario(user),
        'hydra_pin': _hydra_pin_usuario(user),
        'origem': 'importacao_local',
        'conquistas': {
            'unlocked': conquistas_desbloqueadas_total,
            'total': conquistas_total,
            'percent': round((conquistas_desbloqueadas_total / conquistas_total) * 100) if conquistas_total else 0,
        },
    }


def importar_hydra_para_biblioteca_local(meu_email: str, exportacao_json: str) -> tuple[int, int, str | None]:
    user = USUARIOS_DB.get(meu_email)
    if not user:
        return 0, 0, 'Usuário não encontrado.'

    try:
        dados_exportados = json.loads(exportacao_json)
    except json.JSONDecodeError:
        return 0, 0, 'A exportação Hydra precisa estar em JSON válido.'

    jogos_exportados = _hydra_extrair_jogos_exportados(dados_exportados)
    if not jogos_exportados:
        return 0, 0, 'Nenhum jogo foi encontrado nessa exportação Hydra.'

    jogos_importados = 0
    jogos_ja_existiam = 0

    for jogo_exportado in jogos_exportados:
        titulo = jogo_exportado['titulo']
        codigo_origem = jogo_exportado['codigo_origem']

        item_existente = next(
            (
                item
                for item in GerenciadorBiblioteca.obter_biblioteca(meu_email)
                if (getattr(item, 'origem', '') or '').lower() == 'hydra'
                and (getattr(item, 'codigo_origem', '') or '') == codigo_origem
            ),
            None,
        )
        if item_existente:
            jogos_ja_existiam += 1
            continue

        jogo_catalogo = next(
            (
                jogo
                for jogo in JOGOS_DB.values()
                if jogo.titulo.strip().lower() == titulo.strip().lower()
                and jogo.desenvolvedora.lower() == 'hydra'
            ),
            None,
        )
        if not jogo_catalogo:
            novo_id_jogo = max(JOGOS_DB.keys(), default=0) + 1
            jogo_catalogo = Jogo(novo_id_jogo, titulo, 'Hydra', 'Hydra', datetime.now().year)
            try:
                jogo_catalogo.associar_categoria(_obter_ou_criar_categoria('Hydra'))
            except Exception:
                pass
            JOGOS_DB[novo_id_jogo] = jogo_catalogo
            persistir_jogo(jogo_catalogo, getattr(jogo_catalogo, '_categorias', []))

        novo_id_biblioteca = max([b.id for b in BIBLIOTECA_DB.values()], default=0) + 1
        item = GerenciadorBiblioteca.adicionar_jogo(novo_id_biblioteca, meu_email, jogo_catalogo.id)
        item.origem = 'hydra'
        item.codigo_origem = codigo_origem
        item.tempo_jogado_horas = int(round((jogo_exportado['play_seconds'] or 0) / 3600))
        item.conquistas_desbloqueadas = int(jogo_exportado['conquistas_desbloqueadas'] or 0)
        item.conquistas_total = int(jogo_exportado['conquistas_total'] or 0)
        persistir_biblioteca_item(item)
        jogos_importados += 1

    if jogos_importados:
        return jogos_importados, jogos_ja_existiam, None

    return 0, jogos_ja_existiam, 'Nenhum jogo novo foi importado da exportação Hydra.'


def _hydra_importar_contexto_para_biblioteca_local(user, hydra_contexto: dict) -> tuple[int, int]:
    jogos = hydra_contexto.get('jogos') or []
    jogos_importados = 0
    jogos_ja_existiam = 0

    for jogo_hydra in jogos:
        if not isinstance(jogo_hydra, dict):
            continue

        titulo = (jogo_hydra.get('title') or jogo_hydra.get('name') or '').strip()
        if not titulo:
            continue

        codigo_origem = str(jogo_hydra.get('objectId') or jogo_hydra.get('object_id') or jogo_hydra.get('id') or titulo).strip().lower()

        item_existente = next(
            (
                item
                for item in GerenciadorBiblioteca.obter_biblioteca(user.email)
                if (getattr(item, 'origem', '') or '').lower() == 'hydra'
                and (getattr(item, 'codigo_origem', '') or '') == codigo_origem
            ),
            None,
        )
        if item_existente:
            jogos_ja_existiam += 1
            continue

        jogo_catalogo = next(
            (
                jogo
                for jogo in JOGOS_DB.values()
                if jogo.titulo.strip().lower() == titulo.strip().lower()
                and jogo.desenvolvedora.lower() == 'hydra'
            ),
            None,
        )
        if not jogo_catalogo:
            novo_id_jogo = max(JOGOS_DB.keys(), default=0) + 1
            jogo_catalogo = Jogo(novo_id_jogo, titulo, 'Hydra', 'Hydra', datetime.now().year)
            try:
                jogo_catalogo.associar_categoria(_obter_ou_criar_categoria('Hydra'))
            except Exception:
                pass
            JOGOS_DB[novo_id_jogo] = jogo_catalogo
            persistir_jogo(jogo_catalogo, getattr(jogo_catalogo, '_categorias', []))

        chave_biblioteca = f'{user.email}_{jogo_catalogo.id}'
        item = BIBLIOTECA_DB.get(chave_biblioteca)
        if item is None:
            novo_id_biblioteca = max([b.id for b in BIBLIOTECA_DB.values()], default=0) + 1
            item = GerenciadorBiblioteca.adicionar_jogo(novo_id_biblioteca, user.email, jogo_catalogo.id)
        item.origem = 'hydra'
        item.codigo_origem = codigo_origem
        item.cover_url = (jogo_hydra.get('cover_url') or jogo_hydra.get('libraryImageUrl') or jogo_hydra.get('iconUrl') or '')
        item.tempo_jogado_horas = int(round((jogo_hydra.get('playTimeInSeconds') or 0) / 3600))
        item.conquistas_desbloqueadas = int(jogo_hydra.get('achievements_unlocked') or 0)
        item.conquistas_total = int(jogo_hydra.get('achievements_total') or 0)
        persistir_biblioteca_item(item)
        jogos_importados += 1

    return jogos_importados, jogos_ja_existiam


def _hydra_normalizar_capa(jogo: dict) -> str:
    return (
        jogo.get('cover_url')
        or jogo.get('coverUrl')
        or jogo.get('iconUrl')
        or jogo.get('icon_url')
        or jogo.get('heroImageUrl')
        or jogo.get('backgroundImageUrl')
        or _capa_fallback(jogo.get('title') or jogo.get('name') or 'Jogo')
    )


def _hydra_normalizar_jogos(jogos: list[dict]) -> list[dict]:
    resultados = []
    vistos = set()

    for jogo in jogos or []:
        if not isinstance(jogo, dict):
            continue

        object_id = str(jogo.get('objectId') or jogo.get('object_id') or jogo.get('id') or '').strip()
        titulo = (jogo.get('title') or jogo.get('name') or jogo.get('displayName') or object_id or 'Jogo').strip()
        if not object_id:
            object_id = titulo

        if object_id in vistos:
            continue
        vistos.add(object_id)

        tempo_jogado = int(jogo.get('playTimeInSeconds') or jogo.get('playtimeInSeconds') or jogo.get('play_time_in_seconds') or 0)

        resultados.append({
            'objectId': object_id,
            'shop': (jogo.get('shop') or 'hydra').strip() if isinstance(jogo.get('shop'), str) else 'hydra',
            'title': titulo,
            'playTimeInSeconds': tempo_jogado,
            'cover_url': _hydra_normalizar_capa(jogo),
            'isPinned': bool(jogo.get('isPinned')),
            'isFavorite': bool(jogo.get('isFavorite')),
        })

    resultados.sort(key=lambda item: item.get('playTimeInSeconds') or 0, reverse=True)
    return resultados


def montar_hydra_contexto(user) -> dict:
    base_url = DEFAULT_HYDRA_API_BASE_URL
    hydra_usuario = _hydra_usuario_usuario(user)
    hydra_pin = _hydra_pin_usuario(user)
    hydra_token = _hydra_token_usuario(user)
    hydra_email_conta = _hydra_email_conta_usuario(user)
    contexto_local = _hydra_contexto_local(user)

    if contexto_local.get('configurado'):
        return contexto_local

    if hydra_token:
        try:
            perfil = _hydra_fetch_autenticado_json(base_url, '/profile/me', hydra_token)
        except Exception:
            if contexto_local.get('configurado'):
                return contexto_local
            return {
                'configurado': False,
                'erro': 'O token Hydra informado parece inválido ou expirado.',
                'jogos': [],
                'jogos_totais': 0,
                'usuario': None,
                'perfil_url': None,
                'base_url': base_url,
                'email_conta': hydra_email_conta,
                'hydra_usuario': hydra_usuario,
                'hydra_pin': hydra_pin,
            }

        try:
            biblioteca = _hydra_fetch_autenticado_json(
                base_url,
                '/profile/games?take=18&skip=0&sortBy=playedRecently',
                hydra_token,
            )
        except Exception:
            if contexto_local.get('configurado'):
                return contexto_local
            return {
                'configurado': True,
                'erro': 'Não foi possível carregar a biblioteca autenticada da Hydra.',
                'jogos': [],
                'jogos_totais': 0,
                'usuario': perfil if isinstance(perfil, dict) else None,
                'perfil_url': f"{base_url}/users/{(perfil or {}).get('id')}" if isinstance(perfil, dict) and (perfil or {}).get('id') else None,
                'base_url': base_url,
                'email_conta': hydra_email_conta,
                'hydra_usuario': hydra_usuario,
                'hydra_pin': hydra_pin,
            }

        if isinstance(biblioteca, dict):
            jogos = list(
                biblioteca.get('library')
                or biblioteca.get('games')
                or biblioteca.get('items')
                or []
            )
            total = int(biblioteca.get('totalCount') or biblioteca.get('count') or len(jogos))
        else:
            jogos = list(biblioteca or [])
            total = len(jogos)

        jogos_normalizados = _hydra_normalizar_jogos(jogos)

        return {
            'configurado': True,
            'erro': None,
            'jogos': jogos_normalizados[:8],
            'jogos_totais': total,
            'usuario': perfil if isinstance(perfil, dict) else None,
            'perfil_url': f"{base_url}/users/{perfil.get('id')}" if isinstance(perfil, dict) and perfil.get('id') else None,
            'base_url': base_url,
            'email_conta': hydra_email_conta,
            'hydra_usuario': hydra_usuario,
            'hydra_pin': hydra_pin,
        }

    return {
        'configurado': contexto_local.get('configurado', False),
        'erro': contexto_local.get('erro') or 'A Hydra não oferece API pública para integração nativa. Importe uma exportação local em JSON para exibir a biblioteca.',
        'jogos': contexto_local.get('jogos', []),
        'jogos_totais': contexto_local.get('jogos_totais', 0),
        'usuario': contexto_local.get('usuario'),
        'perfil_url': contexto_local.get('perfil_url'),
        'base_url': contexto_local.get('base_url'),
        'email_conta': hydra_email_conta,
        'hydra_usuario': hydra_usuario,
        'hydra_pin': hydra_pin,
        'origem': contexto_local.get('origem', 'importacao_local'),
        'conquistas': contexto_local.get('conquistas'),
    }

    try:
        perfil = _hydra_fetch_json(perfil_url)
    except Exception:
        perfil = {}

    try:
        biblioteca = _hydra_fetch_json(biblioteca_url)
    except Exception as exc:
        return {
            'configurado': True,
            'erro': 'Não foi possível carregar a biblioteca Hydra. Verifique o ID/URL do perfil e a base da API.',
            'jogos': [],
            'jogos_totais': 0,
            'usuario': perfil if isinstance(perfil, dict) else None,
            'perfil_url': perfil_url,
            'base_url': base_url,
            'email_conta': hydra_email_conta,
        }

    if isinstance(biblioteca, dict):
        jogos = list(biblioteca.get('pinnedGames') or []) + list(biblioteca.get('library') or [])
        total = int(biblioteca.get('totalCount') or biblioteca.get('count') or len(jogos))
    else:
        jogos = list(biblioteca or [])
        total = len(jogos)

    jogos_normalizados = _hydra_normalizar_jogos(jogos)

    return {
        'configurado': True,
        'erro': None,
        'jogos': jogos_normalizados[:8],
        'jogos_totais': total,
        'usuario': perfil if isinstance(perfil, dict) else None,
        'perfil_url': perfil_url,
        'base_url': base_url,
        'email_conta': hydra_email_conta,
            'hydra_usuario': hydra_usuario,
            'hydra_pin': hydra_pin,
    }


def _deduplicar_jogos_steam(jogos: list) -> list:
    if not jogos:
        return []

    jogos_unicos = {}
    for jogo in jogos:
        appid = int(jogo.get('appid') or 0)
        if not appid:
            continue

        atual = jogos_unicos.get(appid)
        if not atual or int(jogo.get('playtime_forever') or 0) > int(atual.get('playtime_forever') or 0):
            jogos_unicos[appid] = jogo

    resultado = list(jogos_unicos.values())
    resultado.sort(key=lambda item: int(item.get('playtime_forever') or 0), reverse=True)
    return resultado


def _steam_fetch_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            'User-Agent': 'GameLink/1.0',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        },
    )
    with urlopen(request, timeout=8) as resposta:
        return json.loads(resposta.read().decode('utf-8', errors='replace'))


def _steam_fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            'User-Agent': 'GameLink/1.0',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        },
    )
    with urlopen(request, timeout=8) as resposta:
        return resposta.read().decode('utf-8', errors='replace')


def _steam_post_text(url: str, dados: dict) -> str:
    payload = urlencode(dados).encode('utf-8')
    request = Request(
        url,
        data=payload,
        headers={
            'User-Agent': 'GameLink/1.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        },
    )
    with urlopen(request, timeout=8) as resposta:
        return resposta.read().decode('utf-8', errors='replace')


def _steam_extrair_steamid_de_claimed_id(claimed_id: str) -> str | None:
    correspondencia = re.search(r'/openid/id/(\d{17})$', claimed_id or '')
    if correspondencia:
        return correspondencia.group(1)
    correspondencia = re.search(r'(\d{17})', claimed_id or '')
    return correspondencia.group(1) if correspondencia else None


def _steam_build_openid_url(return_to: str, realm: str) -> str:
    parametros = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': return_to,
        'openid.realm': realm,
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
    }
    return 'https://steamcommunity.com/openid/login?' + urlencode(parametros)


def _steam_verificar_resposta_openid(dados: dict) -> bool:
    parametros = {
        chave: valor for chave, valor in dados.items()
        if chave.startswith('openid.')
    }
    parametros['openid.mode'] = 'check_authentication'
    resposta = _steam_post_text('https://steamcommunity.com/openid/login', parametros)
    return 'is_valid:true' in resposta.replace(' ', '').lower()


def _steam_resolver_steamid(steam_id_ou_vanity: str, api_key: str) -> str | None:
    texto = (steam_id_ou_vanity or '').strip()
    if not texto:
        return None

    correspondencia = re.search(r'\b(\d{17})\b', texto)
    if correspondencia:
        return correspondencia.group(1)

    if '/profiles/' in texto:
        correspondencia = re.search(r'/profiles/(\d{17})', texto)
        if correspondencia:
            return correspondencia.group(1)

    vanity = texto
    if texto.startswith('http'):
        parsed = urlparse(texto)
        if '/id/' in parsed.path:
            vanity = parsed.path.split('/id/', 1)[1].strip('/')
        elif '/profiles/' in parsed.path:
            correspondencia = re.search(r'/profiles/(\d{17})', parsed.path)
            if correspondencia:
                return correspondencia.group(1)
            vanity = parsed.path.strip('/')
        else:
            vanity = parsed.path.strip('/') or texto
    elif '/id/' in texto:
        vanity = texto.split('/id/', 1)[1].strip('/')

    if not api_key or not vanity:
        return None

    url = (
        'https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?'
        f'key={quote(api_key)}&vanityurl={quote(vanity)}'
    )
    dados = _steam_fetch_json(url)
    response = dados.get('response', {}) or {}
    if response.get('success') == 1:
        return response.get('steamid')
    return None


@lru_cache(maxsize=128)
def _steam_owned_games(steam_id64: str, api_key: str) -> list:
    url = (
        'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?'
        f'key={quote(api_key)}&steamid={quote(steam_id64)}'
        '&include_appinfo=1&include_played_free_games=1&format=json'
    )
    try:
        dados = _steam_fetch_json(url)
    except Exception:
        return []

    jogos = dados.get('response', {}).get('games', []) or []
    resultado = []
    for jogo in jogos:
        appid = jogo.get('appid')
        if not appid:
            continue
        resultado.append({
            'appid': appid,
            'name': jogo.get('name') or f'App {appid}',
            'playtime_forever': int(jogo.get('playtime_forever') or 0),
            'cover_url': f'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg',
        })

    return _deduplicar_jogos_steam(resultado)


def _steam_most_played_games_publico(steam_id64: str) -> list:
    if not steam_id64:
        return []

    url = f'https://steamcommunity.com/profiles/{steam_id64}/?xml=1'
    try:
        xml_texto = _steam_fetch_text(url)
    except Exception:
        return []

    try:
        raiz = ET.fromstring(xml_texto)
    except Exception:
        return []

    resultado = []
    for jogo in raiz.findall('.//mostPlayedGames/mostPlayedGame'):
        appid = jogo.findtext('statsName', default='').strip()
        nome = jogo.findtext('gameName', default='').strip()
        horas = jogo.findtext('hoursOnRecord', default='0').strip()
        if not appid:
            link = jogo.findtext('gameLink', default='').strip()
            correspondencia = re.search(r'/app/(\d+)', link)
            if correspondencia:
                appid = correspondencia.group(1)
        if not appid:
            continue

        try:
            horas_float = float(horas or 0)
        except ValueError:
            horas_float = 0.0

        resultado.append({
            'appid': int(appid),
            'name': nome or f'App {appid}',
            'playtime_forever': int(round(horas_float * 60)),
            'cover_url': f'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg',
        })

    return _deduplicar_jogos_steam(resultado)


@lru_cache(maxsize=256)
def _steam_achievements_jogo(steam_id64: str, api_key: str, appid: int) -> dict | None:
    if not appid:
        return None

    url_player = (
        'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/?'
        f'key={quote(api_key)}&steamid={quote(steam_id64)}&appid={appid}&l=pt-BR'
    )
    url_schema = (
        'https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?'
        f'key={quote(api_key)}&appid={appid}&l=pt-BR'
    )

    try:
        dados_player = _steam_fetch_json(url_player)
        dados_schema = _steam_fetch_json(url_schema)
    except Exception:
        return None

    playerstats = dados_player.get('playerstats', {}) or {}
    schema_stats = (dados_schema.get('game', {}) or {}).get('availableGameStats', {}) or {}
    schema_achievements = schema_stats.get('achievements', []) or []
    player_achievements = {item.get('apiname'): item for item in playerstats.get('achievements', []) or []}

    conquistas = []
    for conquista in schema_achievements:
        apiname = conquista.get('name')
        player_item = player_achievements.get(apiname, {})
        unlocked = bool(player_item.get('achieved'))
        conquistas.append({
            'apiname': apiname,
            'title': conquista.get('displayName') or apiname or 'Conquista',
            'description': conquista.get('description') or '',
            'icon': conquista.get('icon') if unlocked else conquista.get('icongray') or conquista.get('icon'),
            'unlocked': unlocked,
            'unlock_time': player_item.get('unlocktime'),
        })

    total = len(conquistas)
    unlocked_total = sum(1 for conquista in conquistas if conquista['unlocked'])

    return {
        'appid': appid,
        'total': total,
        'unlocked': unlocked_total,
        'percent': round((unlocked_total / total) * 100, 1) if total else 0,
        'achievements': conquistas,
    }


@lru_cache(maxsize=256)
def _steam_achievements_publico(steam_id64: str, appid: int) -> dict | None:
    if not steam_id64 or not appid:
        return None

    url = f'https://steamcommunity.com/profiles/{steam_id64}/stats/{appid}/?tab=achievements'

    try:
        html = _buscar_html_com_user_agent(url, timeout=8)
    except Exception:
        return None

    resumo = re.search(r'(\d+)\s+of\s+(\d+)\s+\((\d+)%\)\s+achievements earned', html, re.I)
    unlocked_total = int(resumo.group(1)) if resumo else 0
    total = int(resumo.group(2)) if resumo else 0
    percent = float(resumo.group(3)) if resumo else 0

    class _ParserConquistasPublicas(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.conquistas = []
            self._em_conquista = False
            self._profundidade_div = 0
            self._campo_atual = None
            self._buffer_campo = []
            self._conquista_atual = {}

        def handle_starttag(self, tag, attrs):
            atributos = dict(attrs)
            classes = (atributos.get('class', '') or '').split()

            if tag == 'div' and 'achieveRow' in classes:
                self._em_conquista = True
                self._profundidade_div = 1
                self._campo_atual = None
                self._buffer_campo = []
                self._conquista_atual = {'apiname': None, 'title': '', 'description': '', 'icon': '', 'unlocked': False, 'unlock_time': ''}
                return

            if not self._em_conquista:
                return

            if tag == 'div':
                self._profundidade_div += 1
                if 'achieveUnlockTime' in classes:
                    self._campo_atual = 'unlock_time'
                    self._buffer_campo = []
                return

            if tag == 'img' and not self._conquista_atual.get('icon'):
                self._conquista_atual['icon'] = atributos.get('src', '')
                return

            if tag == 'h3' and 'ellipsis' in classes:
                self._campo_atual = 'title'
                self._buffer_campo = []
                return

            if tag == 'h5':
                self._campo_atual = 'description'
                self._buffer_campo = []

        def handle_endtag(self, tag):
            if not self._em_conquista:
                return

            if self._campo_atual in {'title', 'description', 'unlock_time'} and tag in {'h3', 'h5', 'div'}:
                texto = unescape(''.join(self._buffer_campo)).strip()
                if self._campo_atual == 'unlock_time':
                    self._conquista_atual['unlock_time'] = texto
                    self._conquista_atual['unlocked'] = bool(texto)
                else:
                    self._conquista_atual[self._campo_atual] = texto
                self._campo_atual = None
                self._buffer_campo = []

            if tag == 'div':
                self._profundidade_div -= 1
                if self._profundidade_div <= 0:
                    titulo_limpo = self._conquista_atual.get('title', '').strip() or 'Conquista'
                    descricao_limpa = self._conquista_atual.get('description', '').strip()
                    desbloqueio_limpo = self._conquista_atual.get('unlock_time', '').strip()
                    imagem = self._conquista_atual.get('icon', '')
                    if imagem or titulo_limpo != 'Conquista' or descricao_limpa or desbloqueio_limpo:
                        self.conquistas.append({
                            'apiname': None,
                            'title': titulo_limpo,
                            'description': descricao_limpa,
                            'icon': imagem,
                            'unlocked': bool(desbloqueio_limpo),
                            'unlock_time': desbloqueio_limpo,
                        })
                    self._em_conquista = False
                    self._campo_atual = None
                    self._buffer_campo = []
                    self._conquista_atual = {}

        def handle_data(self, data):
            if self._em_conquista and self._campo_atual:
                self._buffer_campo.append(data)

    parser = _ParserConquistasPublicas()
    parser.feed(html)
    conquistas = parser.conquistas

    if not conquistas:
        return None

    if not total:
        total = len(conquistas)
    if not unlocked_total:
        unlocked_total = len([conquista for conquista in conquistas if conquista['unlocked']])
    if not percent and total:
        percent = round((unlocked_total / total) * 100, 1)

    return {
        'appid': appid,
        'total': total,
        'unlocked': unlocked_total,
        'percent': percent,
        'achievements': conquistas,
        'source': 'steam_publico',
    }


def _buscar_status_steam_usuario(steam_id64: str, api_key: str = '', force_refresh: bool = False) -> dict:
    """
    Busca o status atual do usuário na Steam usando a Web API.
    Steam personastate: 0=offline, 1=online, 2=busy, 3=away, 4=snooze, 5=looking to trade, 6=looking to play
    Retorna um dicionário com as informações de status.
    """
    if not steam_id64:
        return {'online': False, 'game': '', 'appid': None}

    try:
        # Tenta primeiro via API Web (mais confiável)
        api_key = (api_key or os.environ.get('STEAM_API_KEY', '')).strip()
        
        if api_key:
            # Usar a API Web oficial da Steam
            # Adiciona timestamp para force refresh (cache busting)
            timestamp = f'&_t={int(time())}' if force_refresh else ''
            url = (
                'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?'
                f'key={quote(api_key)}&steamids={quote(steam_id64)}&format=json{timestamp}'
            )
            try:
                dados = _steam_fetch_json(url)
                players = dados.get('response', {}).get('players', [])
                
                if players:
                    player = players[0]
                    personastate = int(player.get('personastate', 0) or 0)
                    # Qualquer estado diferente de 0 é online ou visível de alguma forma
                    is_online = personastate != 0
                    
                    # Tenta múltiplas fontes para o nome do jogo (ordem de preferência)
                    current_game = (player.get('gameextrainfo') or '').strip()
                    raw_appid = player.get('gameid')
                    appid = None

                    # Se não tiver gameextrainfo, tenta outros campos
                    if not current_game:
                        current_game = (player.get('gamename') or '').strip()

                    if not current_game:
                        state_msg = (player.get('stateMessage') or '').strip()
                        if state_msg:
                            state_lower = state_msg.lower()
                            for prefix in ['playing ', 'jogando ', 'in-game ', 'in game ', 'em jogo '] :
                                if state_lower.startswith(prefix):
                                    current_game = state_msg[len(prefix):].strip()
                                    break

                            if not current_game:
                                current_game = state_msg

                    # Evita estados genéricos exibidos como jogos
                    if current_game:
                        generic_statuses = {
                            'online', 'offline', 'away', 'busy', 'snooze',
                            'looking to trade', 'looking to play', 'in-game', 'in game',
                            'playing', 'jogando', 'em jogo'
                        }
                        if current_game.lower() in generic_statuses:
                            current_game = ''

                    # Extrai appid quando não houver nome do jogo disponível
                    if raw_appid:
                        try:
                            appid = int(raw_appid)
                            if not current_game and appid > 0 and personastate != 0:
                                current_game = f'[Jogo {appid}]'
                        except (ValueError, TypeError):
                            appid = None

                    resultado = {
                        'online': is_online,
                        'game': current_game or '',
                        'appid': appid,
                    }
                    print(f'[Steam API] {steam_id64}: online={is_online}, game="{current_game}", appid={appid}, raw_response_keys={list(player.keys())}')
                    return resultado
            except Exception as e:
                print(f'[Steam API] Erro: {str(e)}')
                # Fallback para XML se a API falhar
        
        # Fallback: usar XML do perfil público com cache busting
        print(f'[Steam XML] Tentando XML de {steam_id64}')
        timestamp = f'&_t={int(time())}' if force_refresh else ''
        if steam_id64.isdigit():
            url = f'https://steamcommunity.com/profiles/{steam_id64}/?xml=1{timestamp}'
        else:
            url = f'https://steamcommunity.com/id/{quote(steam_id64)}/?xml=1{timestamp}'
        xml_texto = _steam_fetch_text(url)
        
        if not xml_texto or len(xml_texto) < 100:
            print(f'[Steam XML] Resposta vazia')
            return {'online': False, 'game': '', 'appid': None}
        
        raiz = ET.fromstring(xml_texto)

        # Busca o status online
        online_state = (raiz.findtext('onlineState') or 'offline').strip().lower()
        is_online = online_state != 'offline'

        # Busca o jogo
        current_game = (raiz.findtext('gameExtraInfo') or '').strip() or (raiz.findtext('gameFriendlyName') or '').strip() or (raiz.findtext('gameName') or '').strip()
        if not current_game:
            state_msg = (raiz.findtext('stateMessage') or '').strip()
            if state_msg:
                state_lower = state_msg.lower().strip()
                prefixes = ['playing ', 'jogando ', 'in-game ', 'in game ', 'em jogo ']
                for prefix in prefixes:
                    if state_lower.startswith(prefix):
                        current_game = state_msg[len(prefix):].strip()
                        break

                if not current_game:
                    current_game = state_msg

                # Evita estados genéricos como "online", "offline", "away", "busy" etc.
                generic_statuses = {
                    'online', 'offline', 'away', 'busy', 'snooze',
                    'looking to trade', 'looking to play', 'in-game', 'in game',
                    'playing', 'jogando', 'em jogo'
                }
                if current_game and current_game.lower() in generic_statuses:
                    current_game = ''

        # Se estiver online e não tiver jogo, ainda permanece online
        if not current_game and is_online:
            current_game = ''

        # Extrai appid se houver jogo
        appid = None
        if current_game:
            game_link = (raiz.findtext('gameLink') or '').strip()
            m = re.search(r'/app/(\d+)', game_link)
            if m:
                appid = int(m.group(1))

        resultado = {
            'online': is_online,
            'game': current_game or '',
            'appid': appid,
        }
        print(f'[Steam XML] {steam_id64}: {resultado}')
        return resultado
        
    except Exception as e:
        print(f'[Steam] Erro: {str(e)}')
        return {'online': False, 'game': '', 'appid': None}


def sincronizar_status_steam(user_email: str) -> None:
    """
    Sincroniza o status atual da Steam do usuário com o banco de dados.
    """
    meu_email = _normalizar_email(user_email)
    user = USUARIOS_DB.get(meu_email)

    if not user:
        return

    steam_id = _steam_id_ou_vanity_usuario(user)
    api_key = _steam_api_key_usuario(user)

    # Resolve Steam ID se for vanity URL
    if steam_id and not steam_id.isdigit():
        steam_id = _steam_resolver_steamid(steam_id, api_key) or steam_id

    if not steam_id:
        return

    # Busca o status atual com refresh para evitar cache e detectar jogos abertos imediatamente
    status = _buscar_status_steam_usuario(steam_id, api_key, force_refresh=True)

    # Atualiza o usuário
    user.steam_online = status['online']
    user.steam_current_game = status['game'] or ''
    user.steam_current_game_appid = status['appid'] if status['game'] else None
    user.steam_last_update = datetime.now().isoformat()

    # Salva no banco de dados
    _salvar_usuario_no_banco(user)
    
    print(f'[Sincronizar Steam] {user.email}: online={user.steam_online}, game="{user.steam_current_game}", appid={user.steam_current_game_appid}')


def montar_steam_contexto(user, steam_appid: int | None = None) -> dict:
    steam_input = _steam_id_ou_vanity_usuario(user)
    api_key = _steam_api_key_usuario(user)
    steam_id64 = None
    jogos = []
    conquistas = None
    erro = None
    fonte_jogos = 'api'
    capas_usadas: set[str] = set()

    if steam_input:
        steam_id64 = _steam_resolver_steamid(steam_input, api_key)
        if not steam_id64:
            erro = 'Não foi possível resolver sua conta Steam. Cole a URL pública do perfil Steam ou o SteamID64.'
        else:
            if api_key:
                jogos = _steam_owned_games(steam_id64, api_key)
            if not jogos:
                jogos = _steam_most_played_games_publico(steam_id64)
                if jogos:
                    fonte_jogos = 'perfil_publico'
                    if api_key:
                        erro = 'A API oficial não retornou a lista completa, então importei os jogos públicos mais jogados do perfil.'
                else:
                    if api_key:
                        erro = 'A Steam foi encontrada, mas nenhum jogo apareceu. Se o perfil for privado, deixe os detalhes dos jogos como públicos.'
                    else:
                        erro = 'A Steam foi encontrada, mas a lista pública não retornou jogos. Deixe o perfil Steam com jogos públicos.'
            jogos = _deduplicar_jogos_steam(jogos)
            if steam_appid is None and jogos:
                steam_appid = jogos[0]['appid']
            if steam_appid and api_key:
                conquistas = _steam_achievements_jogo(steam_id64, api_key, int(steam_appid))
            if steam_appid and not conquistas:
                conquistas = _steam_achievements_publico(steam_id64, int(steam_appid))

            for jogo in jogos:
                jogo['cover_url'] = _capa_unica_para_lista(
                    jogo.get('title') or jogo.get('name') or 'Jogo',
                    None,
                    capas_usadas,
                )

    jogo_selecionado = None
    if steam_appid and jogos:
        jogo_selecionado = next((jogo for jogo in jogos if int(jogo['appid']) == int(steam_appid)), None)
    if not jogo_selecionado and jogos:
        jogo_selecionado = jogos[0]

    if jogo_selecionado and not jogo_selecionado.get('cover_url'):
        jogo_selecionado['cover_url'] = _capa_unica_para_lista(
            jogo_selecionado.get('title') or jogo_selecionado.get('name') or 'Jogo',
            None,
            capas_usadas,
        )

    return {
        'steam_input': steam_input,
        'steam_id64': steam_id64,
        'api_key_configurada': bool(api_key),
        'jogos': jogos[:18],
        'jogo_selecionado': jogo_selecionado,
        'steam_appid': int(steam_appid) if steam_appid else None,
        'conquistas': conquistas,
        'erro': erro,
        'fonte_jogos': fonte_jogos,
        'configurado': bool(steam_id64),
    }


def montar_biblioteca_cards(email: str) -> list:
    cards = []
    capas_usadas: set[str] = set()
    for item in GerenciadorBiblioteca.obter_biblioteca(email):
        jogo = JOGOS_DB.get(item.jogo_id)
        if not jogo:
            continue

        categorias = [categoria.lower() for categoria in jogo.listar_categorias()]
        origem = (getattr(item, 'origem', '') or '').strip().lower()
        if origem == 'hydra':
            fonte = 'hydra'
        elif origem == 'steam' or 'steam' in categorias or 'meus jogos' in categorias:
            fonte = 'steam'
        else:
            fonte = 'manual'

        cards.append({
            'item': item,
            'jogo': jogo,
            'capa_url': (getattr(item, 'cover_url', '') or _capa_para_jogo_catalogo(jogo, capas_usadas)),
            'capa_fallback': _capa_fallback(jogo.titulo),
            'esta_na_biblioteca': True,
            'origem': fonte,
        })
    return cards


def _obter_ou_criar_categoria(nome_categoria: str) -> Categoria:
    categoria_existente = next(
        (cat for cat in CATEGORIAS_DB.values() if cat.nome.strip().lower() == nome_categoria.strip().lower()),
        None,
    )
    if categoria_existente:
        return categoria_existente

    novo_id_categoria = max(CATEGORIAS_DB.keys(), default=0) + 1
    categoria = Categoria(novo_id_categoria, nome_categoria)
    CATEGORIAS_DB[novo_id_categoria] = categoria
    persistir_categoria(categoria)
    return categoria


def _steam_jogo_para_catalogo(jogo_steam: dict) -> Jogo:
    appid = int(jogo_steam.get('appid') or 0)
    nome = (jogo_steam.get('name') or f'App {appid}').strip()
    jogo = Jogo(appid, nome, 'Steam', 'Steam', datetime.now().year)
    try:
        jogo.associar_categoria(_obter_ou_criar_categoria('Steam'))
        jogo.associar_categoria(_obter_ou_criar_categoria('Meus jogos'))
    except Exception:
        pass
    jogo.capa_url = _capa_steam_jogo(appid)
    jogo.capa_fallback = _capa_fallback(nome)
    return jogo


def importar_steam_para_biblioteca_local(meu_email: str) -> tuple[int, int, str | None]:
    user = USUARIOS_DB.get(meu_email)
    if not user:
        return 0, 0, 'Usuário não encontrado.'

    steam_contexto = montar_steam_contexto(user)
    if not steam_contexto.get('configurado') and not steam_contexto.get('jogos'):
        return 0, 0, 'Conecte sua Steam com URL pública ou SteamID64 antes de importar. A Steam API Key é opcional para conquistas.'

    jogos_importados = 0
    jogos_ja_existiam = 0

    for jogo_steam in steam_contexto.get('jogos', []):
        appid = int(jogo_steam.get('appid') or 0)
        if not appid:
            continue

        if appid not in JOGOS_DB:
            jogo_catalogo = _steam_jogo_para_catalogo(jogo_steam)
            JOGOS_DB[appid] = jogo_catalogo
            persistir_jogo(jogo_catalogo, jogo_catalogo._categorias)

        if GerenciadorBiblioteca.jogo_na_biblioteca(meu_email, appid):
            jogos_ja_existiam += 1
            continue

        try:
            novo_id_biblioteca = max([b.id for b in BIBLIOTECA_DB.values()], default=0) + 1
            item = GerenciadorBiblioteca.adicionar_jogo(novo_id_biblioteca, meu_email, appid)
            horas_jogadas = int(round((jogo_steam.get('playtime_forever') or 0) / 60))
            item.atualizar_tempo_jogado(horas_jogadas)
            item.cover_url = _capa_steam_jogo(appid)
            persistir_biblioteca_item(item)
            jogos_importados += 1
        except Exception:
            continue

    erro = None
    if jogos_importados:
        if steam_contexto.get('fonte_jogos') == 'perfil_publico':
            erro = 'Importei os jogos públicos mais jogados do perfil, porque a API oficial não retornou a lista completa.'
    elif not jogos_ja_existiam:
        erro = steam_contexto.get('erro') or 'Nenhum jogo da Steam foi importado.'

    return jogos_importados, jogos_ja_existiam, erro


def montar_amigos_contexto(email: str) -> dict:
    amigos_emails = GerenciadorAmigos.obter_amigos(email)
    amigos = [USUARIOS_DB.get(amigo_email) for amigo_email in amigos_emails if USUARIOS_DB.get(amigo_email)]
    pendentes = GerenciadorAmigos.obter_solicitacoes_pendentes(email)
    pendentes_emails = {sol.email_solicitante for sol in pendentes}
    sugeridos = []

    for amigo_email, usuario in USUARIOS_DB.items():
        if amigo_email == email:
            continue
        if amigo_email in amigos_emails:
            continue
        if amigo_email in pendentes_emails:
            continue
        if GerenciadorAmigos.sao_amigos(email, amigo_email):
            continue
        sugeridos.append({
            'email': amigo_email,
            'nome': usuario.nome,
        })

    return {
        'amigos_emails': amigos_emails,
        'amigos': amigos,
        'pendentes': pendentes,
        'sugeridos': sugeridos,
    }

# Moderação de Conteúdo Dinâmica (Suporta o arquivo com espaço ou corrigido)
import importlib.util
try:
    spec = importlib.util.spec_from_file_location("moderacao", "modelos/moderação de conteudo.py")
    moderacao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(moderacao)
    moderate_text = moderacao.moderate_text
except Exception:
    def moderate_text(texto):
        proibidas = ['spam', 'ofensa', 'impróprio']
        achados = [p for p in proibidas if p in texto.lower()]
        return {"allowed": len(achados) == 0, "blocked_terms": achados}

# Carga inicial de dados unificada
_estado_persistido = carregar_estado_persistido()
CATEGORIAS_DB = _estado_persistido.get('categorias_db', {})
if not JOGOS_DB:
    c1 = Categoria(1, "RPG")
    c2 = Categoria(2, "Ação")
    CATEGORIAS_DB[1] = c1
    CATEGORIAS_DB[2] = c2
    persistir_categoria(c1)
    persistir_categoria(c2)

    j1 = Jogo(1, "The Witcher 3", "RPG", "CD Projekt Red", 2015)
    j1.associar_categoria(c1)
    j2 = Jogo(2, "Elden Ring", "RPG", "FromSoftware", 2022)
    j2.associar_categoria(c1)
    j3 = Jogo(3, "GTA V", "Ação", "Rockstar", 2013)
    j3.associar_categoria(c2)

    JOGOS_DB[1] = j1
    JOGOS_DB[2] = j2
    JOGOS_DB[3] = j3
    persistir_jogo(j1, [c1])
    persistir_jogo(j2, [c1])
    persistir_jogo(j3, [c2])

    if "admin@gamelink.com" not in USUARIOS_DB:
        admin = Admin(1, "Caxa", "admin@gamelink.com", "admin123", nivel_acesso=5)
        USUARIOS_DB[admin.email.lower()] = admin
        persistir_usuario(admin)

# --- Rotas de Autenticação ---
@app.route('/')
def index(): 
    return redirect(url_for('login'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        acao = (request.form.get('acao') or 'iniciar').strip().lower()

        if acao in {'verificar', 'reenviar'}:
            pendente = _cadastro_pendente_valido()
            if not pendente:
                flash('Sua verificação expirou. Faça o cadastro novamente.', 'warning')
                return render_template('cadastro.html', verificacao_pendente=False)

            if acao == 'reenviar':
                novo_codigo = _gerar_codigo_verificacao()
                pendente['codigo'] = novo_codigo
                pendente['expira_em'] = time() + 600
                session['cadastro_pendente'] = pendente
                try:
                    if _enviar_codigo_verificacao_email(pendente['email'], novo_codigo, pendente['nome']):
                        flash('Novo código enviado para seu e-mail.', 'info')
                        codigo_local = None
                    else:
                        flash('SMTP não configurado. O código foi exibido localmente para teste.', 'warning')
                        codigo_local = novo_codigo
                except Exception as exc:
                    flash(f'Não foi possível reenviar o código: {exc}', 'danger')
                    codigo_local = pendente.get('codigo')
                return render_template('cadastro.html', verificacao_pendente=True, email_pendente=pendente['email'], codigo_local=codigo_local)

            codigo_informado = (request.form.get('codigo_verificacao') or '').strip()
            if codigo_informado != pendente.get('codigo'):
                flash('Código de verificação inválido.', 'danger')
                return render_template('cadastro.html', verificacao_pendente=True, email_pendente=pendente['email'])

            email = pendente['email']
            nome = pendente['nome']
            senha = pendente['senha']
            if email in USUARIOS_DB:
                session.pop('cadastro_pendente', None)
                flash('E-mail já cadastrado!', 'danger')
                return render_template('cadastro.html', verificacao_pendente=False)

            proximo_id = max([user.id for user in USUARIOS_DB.values()], default=0) + 1
            novo_usuario = Usuario(proximo_id, nome, email, senha)
            USUARIOS_DB[email] = novo_usuario
            persistir_usuario(novo_usuario)
            session.pop('cadastro_pendente', None)
            flash('E-mail verificado. Cadastro concluído!', 'success')
            return redirect(url_for('login'))

        nome = request.form['nome'].strip()
        email = _normalizar_email(request.form['email'])
        senha = request.form['senha']
        if email in USUARIOS_DB:
            flash("E-mail já cadastrado!", "danger")
        else:
            codigo = _gerar_codigo_verificacao()
            session['cadastro_pendente'] = {
                'nome': nome,
                'email': email,
                'senha': senha,
                'codigo': codigo,
                'expira_em': time() + 600,
            }
            try:
                if _enviar_codigo_verificacao_email(email, codigo, nome):
                    flash('Enviamos um código de verificação para o seu e-mail.', 'info')
                    codigo_local = None
                else:
                    flash('SMTP não configurado. O código foi exibido localmente para teste.', 'warning')
                    codigo_local = codigo
                return render_template('cadastro.html', verificacao_pendente=True, email_pendente=email, codigo_local=codigo_local)
            except Exception as exc:
                flash(f'Não foi possível enviar o e-mail de verificação: {exc}', 'danger')
                return render_template('cadastro.html', verificacao_pendente=True, email_pendente=email, codigo_local=codigo)
    pendente = _cadastro_pendente_valido()
    return render_template('cadastro.html', verificacao_pendente=bool(pendente), email_pendente=(pendente or {}).get('email'), codigo_local=(pendente or {}).get('codigo'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = _normalizar_email(request.form['email'])
        senha = request.form['senha']
        user = USUARIOS_DB.get(email)
        if user and user.verificar_senha(senha):
            session['user_email'] = user.email
            session['user_nome'] = user.nome
            session['is_admin'] = isinstance(user, Admin)
            ONLINE_USERS.add(user.email)
            return redirect(url_for('dashboard'))
        flash("Credenciais inválidas.", "danger")
    return render_template('login.html')

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form['email']
        user = USUARIOS_DB.get(email)
        if user:
            user.token_recuperacao = "123XYZ"
            flash(f"Token gerado para {email}. (Use: 123XYZ)", "info")
            return render_template('recuperar.html', email=email, token_gerado=True)
        flash("E-mail não encontrado.", "danger")
    return render_template('recuperar.html', token_gerado=False)


@app.route('/steam/conectar')
def steam_conectar():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    return_to = url_for('steam_callback', _external=True)
    realm = request.host_url
    return redirect(_steam_build_openid_url(return_to, realm))


@app.route('/steam/callback')
def steam_callback():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    dados = request.values.to_dict(flat=True)
    if dados.get('openid.mode') != 'id_res':
        flash('Falha ao conectar com a Steam.', 'danger')
        return redirect(url_for('perfil', email=meu_email))

    try:
        if not _steam_verificar_resposta_openid(dados):
            flash('Não foi possível validar sua conta Steam.', 'danger')
            return redirect(url_for('perfil', email=meu_email))
    except Exception:
        flash('Não foi possível validar sua conta Steam.', 'danger')
        return redirect(url_for('perfil', email=meu_email))

    claimed_id = dados.get('openid.claimed_id') or dados.get('openid.identity') or ''
    steam_id64 = _steam_extrair_steamid_de_claimed_id(claimed_id)
    if not steam_id64:
        flash('Não foi possível identificar seu SteamID64.', 'danger')
        return redirect(url_for('perfil', email=meu_email))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('login'))

    user.steam_id64 = steam_id64
    persistir_usuario(user)

    jogos_importados, jogos_ja_existiam, erro_steam = importar_steam_para_biblioteca_local(meu_email)
    if jogos_importados:
        flash(f'Steam conectada e {jogos_importados} jogo(s) foram importados para sua biblioteca.', 'success')
    elif jogos_ja_existiam:
        flash('Steam conectada. Sua biblioteca local já estava sincronizada.', 'info')
    elif erro_steam:
        flash(f'Steam conectada, mas a biblioteca não pôde ser importada: {erro_steam}', 'warning')
    else:
        flash('Steam conectada, mas nenhum jogo foi importado.', 'warning')

    return redirect(url_for('perfil', email=meu_email))

@app.route('/hydra_cache_load')
def hydra_cache_load():
    """Carrega o cache local do Hydra e importa para a biblioteca do usuário.
    
    Similar ao steam_callback, esta rota:
    1. Verifica se Hydra está ativo localmente
    2. Sincroniza o estado do Hydra
    3. Importa jogos do cache local para a biblioteca
    4. Redireciona para o perfil
    """
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(_normalizar_email(meu_email))
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('login'))

    # Verifica se Hydra está ativo localmente
    if not _hydra_local_ativo_real():
        flash('Hydra não está em execução. Inicie o Hydra para sincronizar o cache.', 'warning')
        return redirect(url_for('perfil', email=meu_email))

    try:
        # Sincroniza o estado real do Hydra
        _hydra_sincronizar_estado_real(user)
        persistir_usuario(user)
        
        # Obtém o contexto do Hydra (cache local)
        hydra_contexto = montar_hydra_contexto(user)
        
        if not hydra_contexto.get('configurado'):
            flash('Cache do Hydra não encontrado. Importe seus jogos do Hydra primeiro.', 'warning')
            return redirect(url_for('perfil', email=meu_email))
        
        # Importa jogos do cache Hydra para a biblioteca local
        jogos_importados, jogos_ja_existiam = _hydra_importar_contexto_para_biblioteca_local(user, hydra_contexto)
        
        if jogos_importados:
            flash(f'✅ Hydra sincronizado com sucesso! {jogos_importados} jogo(s) foram importados para sua biblioteca.', 'success')
        elif jogos_ja_existiam:
            flash('✅ Hydra sincronizado! Sua biblioteca local já contém esses jogos.', 'info')
        else:
            flash('⚠️ Hydra sincronizado, mas nenhum jogo novo foi encontrado.', 'warning')
        
        # Recarrega o usuário do banco para obter dados sincronizados
        user_updated = USUARIOS_DB.get(_normalizar_email(meu_email))
        if user_updated:
            _hydra_sincronizar_estado_real(user_updated)
            persistir_usuario(user_updated)
            print(f'[Hydra Cache Load] Sincronizado para {meu_email}: game="{user_updated.hydra_current_game}"')
    
    except Exception as e:
        print(f'[Hydra Cache Load] Erro: {e}')
        flash(f'Erro ao sincronizar cache do Hydra: {str(e)}', 'danger')
    
    return redirect(url_for('perfil', email=meu_email))

@app.route('/redefinir', methods=['POST'])
def redefinir():
    email = request.form['email']
    token = request.form['token']
    nova_senha = request.form['nova_senha']
    user = USUARIOS_DB.get(email)
    if user:
        try:
            user.alterar_senha_com_token(token, nova_senha)
            flash("Senha redefinida com sucesso!", "success")
            return redirect(url_for('login'))
        except AutenticacaoError as e:
            flash(str(e), "danger")
    return redirect(url_for('recuperar'))

# --- Rotas de Dashboard e Jogos ---
@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    
    meu_email = session['user_email']
    # Sincroniza automaticamente o status Steam ao carregar o dashboard,
    # mas somente se o usuário tiver `steam_id64` e o último update for antigo.
    try:
        user_for_sync = USUARIOS_DB.get(_normalizar_email(meu_email))
        if user_for_sync:
            _hydra_atualizar_status_local(user_for_sync)
            persistir_usuario(user_for_sync)

            if getattr(user_for_sync, 'steam_id64', ''):
                should_sync = False
                if not getattr(user_for_sync, 'steam_last_update', None):
                    should_sync = True
                else:
                    try:
                        last_dt = datetime.fromisoformat(user_for_sync.steam_last_update)
                        if datetime.now() - last_dt > timedelta(seconds=60):
                            should_sync = True
                    except Exception:
                        should_sync = True

                if should_sync:
                    try:
                        sincronizar_status_steam(meu_email)
                        # Recarrega o usuário do banco para obter dados sincronizados
                        user_for_sync = USUARIOS_DB.get(_normalizar_email(meu_email))
                        if user_for_sync:
                            _hydra_atualizar_status_local(user_for_sync)
                            persistir_usuario(user_for_sync)
                            print(f'[Dashboard Init] Steam sincronizado para {meu_email}: online={user_for_sync.steam_online}, game="{user_for_sync.steam_current_game}", hydra="{user_for_sync.hydra_current_game}"')
                    except Exception as e:
                        print(f'[Dashboard Init] Erro ao sincronizar Steam: {e}')
    except Exception:
        pass
    jogos = list(JOGOS_DB.values())
    capas_usadas: set[str] = set()
    for jogo in jogos:
        jogo.capa_url = _capa_para_jogo_catalogo(jogo, capas_usadas)
        jogo.capa_fallback = _capa_fallback(jogo.titulo)

    posts_visiveis = {k: v for k, v in POSTS_DB.items() if v.visivel}
    comentarios_visiveis = [c for c in COMENTARIOS_POSTS_DB if c.visivel]
    notif_list = GerenciadorNotificacoes.obter_notificacoes(meu_email)
    notif_nao_lidas = GerenciadorNotificacoes.contar_nao_lidas(meu_email)
    biblioteca_cards = montar_biblioteca_cards(meu_email)
    contexto_amigos = montar_amigos_contexto(meu_email)
    amigos_ativos = [amigo for amigo in contexto_amigos['amigos'] if esta_online(amigo.email)]
    
    return render_template(
        'dashboard.html', 
        jogos=jogos, 
        usuarios=USUARIOS_DB, 
        posts=posts_visiveis, 
        comentarios_posts=comentarios_visiveis, 
        notif_nao_lidas=notif_nao_lidas,
        notificacoes=notif_list,
        biblioteca_cards=biblioteca_cards,
        amigos=contexto_amigos['amigos'],
        amigos_ativos=amigos_ativos,
        amigos_emails=contexto_amigos['amigos_emails'],
        solicitacoes_pendentes=contexto_amigos['pendentes'],
        usuarios_sugeridos=contexto_amigos['sugeridos'],
        hydra_local_ativa=_hydra_local_ativo_real()
    )

@app.route('/jogos/novo', methods=['POST'])
def novo_jogo():
    if not session.get('is_admin'): 
        return redirect(url_for('dashboard'))
    try:
        novo_id = max(JOGOS_DB.keys(), default=0) + 1
        jogo = Jogo(novo_id, request.form['titulo'], request.form['genero'], request.form['desenvolvedora'], int(request.form['ano']))
        
        # Garante amarração de Categoria (RF10)
        categoria_existente = next((c for c in CATEGORIAS_DB.values() if c.nome.lower() == jogo.genero.lower()), None)
        if not categoria_existente:
            id_cat = len(CATEGORIAS_DB) + 1
            categoria_existente = Categoria(id_cat, jogo.genero)
            CATEGORIAS_DB[id_cat] = categoria_existente
            persistir_categoria(categoria_existente)
        jogo.associar_categoria(categoria_existente)
        
        JOGOS_DB[novo_id] = jogo
        persistir_jogo(jogo, [categoria_existente])
        flash("Jogo cadastrado!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('dashboard'))

@app.route('/jogos/deletar/<int:id>', methods=['POST'])
def deletar_jogo(id):
    if session.get('is_admin') and id in JOGOS_DB: 
        del JOGOS_DB[id]
        remover_jogo(id)
        flash("Jogo deletado!", "success")
    return redirect(url_for('dashboard'))

# --- Busca Avançada (RF13) ---
@app.route('/busca')
def busca():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    meu_email = session['user_email']
    termo = request.args.get('termo', '').lower()
    filtro = request.args.get('filtro', 'titulo')
    resultados = []

    capas_usadas: set[str] = set()
    for jogo in JOGOS_DB.values():
        if filtro == 'titulo' and termo in jogo.titulo.lower():
            resultados.append(jogo)
        elif filtro == 'genero' and termo in jogo.genero.lower():
            resultados.append(jogo)

    for jogo in resultados:
        jogo.capa_url = _capa_para_jogo_catalogo(jogo, capas_usadas)
        jogo.capa_fallback = _capa_fallback(jogo.titulo)

    posts_visiveis = {k: v for k, v in POSTS_DB.items() if v.visivel}
    comentarios_visiveis = [c for c in COMENTARIOS_POSTS_DB if c.visivel]
    notif_list = GerenciadorNotificacoes.obter_notificacoes(meu_email)
    notif_nao_lidas = GerenciadorNotificacoes.contar_nao_lidas(meu_email)
    biblioteca_cards = montar_biblioteca_cards(meu_email)
    contexto_amigos = montar_amigos_contexto(meu_email)

    return render_template(
        'dashboard.html',
        jogos=resultados,
        usuarios=USUARIOS_DB,
        posts=posts_visiveis,
        comentarios_posts=comentarios_visiveis,
        notif_nao_lidas=notif_nao_lidas,
        notificacoes=notif_list,
        biblioteca_cards=biblioteca_cards,
        amigos=contexto_amigos['amigos'],
        amigos_emails=contexto_amigos['amigos_emails'],
        solicitacoes_pendentes=contexto_amigos['pendentes'],
        usuarios_sugeridos=contexto_amigos['sugeridos'],
        busca_termo=termo,
        filtro_selecionado=filtro
    )

# --- Funcionalidades de Rede Social ---
@app.route('/perfil/<email>')
def perfil(email):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    user = USUARIOS_DB.get(email)
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))

    meu_email = session.get('user_email')
    if email == meu_email:
        _hydra_atualizar_status_local(user)

    amigos = GerenciadorAmigos.obter_amigos(email)
    steam_contexto = montar_steam_contexto(user, request.args.get('steam_appid', type=int))
    hydra_contexto = montar_hydra_contexto(user)
    reviews_usuario = []
    for review in GerenciadorReviews.obter_reviews_usuario(email):
        jogo = JOGOS_DB.get(review.jogo_id)
        comentarios = GerenciadorReviews.obter_comentarios_review(review.id)
        reviews_usuario.append({
            'id': review.id,
            'titulo': review.titulo,
            'conteudo': review.conteudo,
            'nota': review.nota,
            'jogo_titulo': jogo.titulo if jogo else f'Jogo #{review.jogo_id}',
            'data': review.data_criacao.strftime('%d/%m/%Y'),
            'total_comentarios': len(comentarios),
            'comentarios': [
                {
                    'id': comentario.id,
                    'autor_email': comentario.email_usuario,
                    'autor_nome': USUARIOS_DB.get(comentario.email_usuario).nome if USUARIOS_DB.get(comentario.email_usuario) else comentario.email_usuario,
                    'texto': comentario.texto,
                    'data': comentario.data_criacao.strftime('%d/%m/%Y %H:%M')
                }
                for comentario in comentarios
            ]
        })
    
    # === SISTEMA DE RELACIONAMENTO DEDICADO ===
    sao_amigos = False
    tem_solicitacao_pendente = False
    usuarios_ativos_disponiveis = []
    
    if meu_email and meu_email != email:
        sao_amigos = GerenciadorAmigos.sao_amigos(meu_email, email)
        
        solicitacoes_para_mim = GerenciadorAmigos.obter_solicitacoes_pendentes(meu_email)
        for sol in solicitacoes_para_mim:
            if sol.email_solicitante == email:
                tem_solicitacao_pendente = True
                break

    amigos_emails = set(GerenciadorAmigos.obter_amigos(meu_email)) if meu_email else set()
    pendentes_comigo = set()
    if meu_email:
        for solicitacao in AMIZADES_DB.values():
            if solicitacao.status != 'pendente':
                continue
            if solicitacao.email_solicitante == meu_email:
                pendentes_comigo.add(solicitacao.email_receptor)
            elif solicitacao.email_receptor == meu_email:
                pendentes_comigo.add(solicitacao.email_solicitante)

    if meu_email:
        usuarios_ativos_disponiveis = sorted(
            [
                usuario
                for usuario in USUARIOS_DB.values()
                if usuario.email != meu_email
                and usuario.email not in amigos_emails
                and usuario.email not in pendentes_comigo
                and esta_online(usuario.email)
            ],
            key=lambda usuario: usuario.nome.lower()
        )

    return render_template(
        'perfil.html', 
        usuario=user, 
        amigos=amigos, 
        usuarios=USUARIOS_DB, 
        jogos=list(JOGOS_DB.values()),
        comentarios=[c for c in COMENTARIOS_POSTS_DB if c.visivel],
        biblioteca_cards=montar_biblioteca_cards(email),
        reviews_usuario=reviews_usuario,
        steam_contexto=steam_contexto,
        hydra_contexto=hydra_contexto,
        hydra_local_ativa=(email == meu_email and _hydra_local_ativo_real()),
        sao_amigos=sao_amigos,
        tem_solicitacao_pendente=tem_solicitacao_pendente,
        usuarios_ativos_disponiveis=usuarios_ativos_disponiveis
    )

@app.route('/perfil/editar')
def editar_perfil():
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    user = USUARIOS_DB.get(session['user_email'])
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    return render_template('editar_perfil.html', usuario=user)

@app.route('/perfil/salvar', methods=['POST'])
def salvar_perfil():
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    user = USUARIOS_DB.get(session['user_email'])
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))

    acao = (request.form.get('acao') or 'salvar_perfil').strip()
    
    servidor_anterior = user.discord_server
    user.nome = request.form.get('nome', user.nome)
    idade_str = request.form.get('idade', '').strip()
    user.idade = int(idade_str) if idade_str else None
    user.gosto_jogos = request.form.get('gosto_jogos', '')
    user.telefone = request.form.get('telefone', '')
    user.discord_tag = request.form.get('discord_tag', '').strip()
    user.discord_server = request.form.get('discord_server', '').strip()
    user.discord_online = request.form.get('discord_online') == '1'
    if 'foto_perfil' in request.form:
        user.foto_perfil = request.form.get('foto_perfil', '').strip()
    if 'foto_perfil_upload' in request.files:
        file = request.files['foto_perfil_upload']
        if file and file.filename and allowed_file(file.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filename = secure_filename(f"{session['user_email']}_{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            user.foto_perfil = f"/static/uploads/{filename}"
    if 'steam_id64' in request.form:
        user.steam_id64 = request.form.get('steam_id64', '').strip()
    if 'steam_api_key' in request.form:
        user.steam_api_key = request.form.get('steam_api_key', '').strip()
    if 'hydra_account_email' in request.form:
        user.hydra_account_email = request.form.get('hydra_account_email', '').strip()
    if 'hydra_usuario' in request.form:
        user.hydra_usuario = request.form.get('hydra_usuario', '').strip()
    if 'hydra_pin' in request.form:
        user.hydra_pin = request.form.get('hydra_pin', '').strip()
    if 'hydra_token' in request.form:
        user.hydra_token = request.form.get('hydra_token', '').strip()
    
    session['user_nome'] = user.nome
    persistir_usuario(user)

    if user.discord_server and user.discord_server != servidor_anterior:
        flash("Servidor Discord configurado! Abrindo o convite...", "success")
        return redirect(user.obter_link_discord() or url_for('perfil', email=session['user_email']))

    flash("Perfil atualizado com sucesso!", "success")
    return redirect(url_for('perfil', email=session['user_email']))


@app.route('/hydra/conectar', methods=['GET', 'POST'])
@app.route('/hydra/login', methods=['GET', 'POST'])
def hydra_conectar():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('dashboard'))

    hydra_profile_id = getattr(user, 'hydra_profile_id', '') or ''
    hydra_api_base_url = getattr(user, 'hydra_api_base_url', '') or DEFAULT_HYDRA_API_BASE_URL
    hydra_account_email = _hydra_email_conta_usuario(user)
    hydra_usuario = _hydra_usuario_usuario(user)
    hydra_pin = _hydra_pin_usuario(user)
    hydra_token = _hydra_token_usuario(user)
    hydra_entrada = hydra_token or hydra_profile_id
    hydra_token_local = _hydra_token_local_detectado()

    if request.method == 'GET':
        return redirect(url_for('perfil', email=meu_email) + '#hydra-games-section')

    if request.method == 'POST':
        hydra_account_email = request.form.get('hydra_account_email', '').strip()
        hydra_usuario = request.form.get('hydra_usuario', '').strip()
        hydra_pin = request.form.get('hydra_pin', '').strip()
        hydra_token = request.form.get('hydra_entrada', '').strip() or request.form.get('hydra_token', '').strip()
        hydra_entrada = hydra_token or hydra_usuario or hydra_pin

        if not hydra_entrada:
            flash('Preencha o token Hydra ou o ID/URL do perfil.', 'warning')
        else:
            user.hydra_token = hydra_token
            user.hydra_profile_id = ''
            user.hydra_usuario = hydra_usuario
            user.hydra_pin = hydra_pin
            user.hydra_account_email = hydra_account_email
            persistir_usuario(user)
            flash('Conexão Hydra salva com sucesso.', 'success')
            return redirect(url_for('perfil', email=meu_email) + '#hydra-games-section')

    return render_template(
        'hydra_login.html',
        usuario=user,
        hydra_contexto=montar_hydra_contexto(user),
        hydra_entrada=hydra_entrada,
        hydra_token_local=hydra_token_local,
        hydra_account_email=hydra_account_email,
        hydra_usuario=hydra_usuario,
        hydra_pin=hydra_pin,
    )


@app.route('/hydra/detectar-sessao', methods=['POST'])
def hydra_detectar_sessao_local():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('hydra_conectar'))

    jogos_cacheados, display_name_cacheado = _hydra_cache_local_jogos()
    if not jogos_cacheados:
        flash('Não encontrei cache local da Hydra neste PC.', 'warning')
        return redirect(url_for('hydra_conectar'))

    jogos_para_importar = _hydra_normalizar_jogos(jogos_cacheados)

    jogos_importados, jogos_ja_existiam = _hydra_importar_contexto_para_biblioteca_local(user, {'jogos': jogos_para_importar})

    if jogos_importados:
        flash(f'Cache local da Hydra detectado. {jogos_importados} jogo(s) foram importados para sua biblioteca.', 'success')
    elif jogos_ja_existiam:
        flash('Cache local da Hydra detectado. Sua biblioteca local já estava atualizada.', 'info')
    else:
        flash('Cache local da Hydra detectado, mas nenhum jogo foi carregado para a biblioteca.', 'warning')

    return redirect(url_for('minha_biblioteca', filtro='hydra'))


@app.route('/hydra/importar', methods=['POST'])
def importar_hydra_exportacao():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('hydra_conectar'))

    arquivo = request.files.get('hydra_exportacao')
    if not arquivo or not getattr(arquivo, 'filename', ''):
        flash('Envie um arquivo JSON de exportação da Hydra.', 'warning')
        return redirect(url_for('hydra_conectar'))

    try:
        exportacao_json = arquivo.read().decode('utf-8-sig').strip()
    except UnicodeDecodeError:
        flash('A exportação Hydra precisa estar em UTF-8.', 'warning')
        return redirect(url_for('hydra_conectar'))

    if not exportacao_json:
        flash('O arquivo de exportação da Hydra está vazio.', 'warning')
        return redirect(url_for('hydra_conectar'))

    jogos_importados, jogos_ja_existiam, erro_hydra = importar_hydra_para_biblioteca_local(meu_email, exportacao_json)

    if jogos_importados:
        flash(f'{jogos_importados} jogo(s) da Hydra foram importados para sua biblioteca local.', 'success')
    elif jogos_ja_existiam:
        flash('Sua biblioteca local já tinha esses jogos da Hydra importados.', 'info')
    elif erro_hydra:
        flash(erro_hydra, 'warning')
    else:
        flash('Nenhum jogo da Hydra foi importado.', 'warning')

    return redirect(url_for('hydra_conectar'))


@app.route('/steam/sincronizar', methods=['POST'])
def sincronizar_steam():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    jogos_importados, jogos_ja_existiam, erro_steam = importar_steam_para_biblioteca_local(meu_email)
    if jogos_importados:
        flash(f'Steam sincronizada com {jogos_importados} jogo(s) importado(s).', 'success')
    elif jogos_ja_existiam:
        flash('Sua biblioteca local já estava sincronizada com a Steam.', 'info')
    elif erro_steam:
        flash(erro_steam, 'warning')
    else:
        flash('Nenhum jogo da Steam foi importado.', 'warning')

    return redirect(request.referrer or url_for('perfil', email=meu_email))


@app.route('/steam/sync-agora')
def sync_steam_agora():
    """Sincronização agressiva com cache busting - atualiza o status instantaneamente"""
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'erro': 'Não autenticado'}), 401

    user = USUARIOS_DB.get(_normalizar_email(meu_email))
    if not user:
        return jsonify({'erro': 'Usuário não encontrado'}), 404
    
    steam_id = _steam_id_ou_vanity_usuario(user)
    api_key = _steam_api_key_usuario(user)
    
    if steam_id and not steam_id.isdigit():
        steam_id = _steam_resolver_steamid(steam_id, api_key) or steam_id
    
    if not steam_id:
        return jsonify({'erro': 'Steam ID não configurada'}), 400
    
    # Busca com force_refresh=True para contornar cache e usar a API key do usuário
    status = _buscar_status_steam_usuario(steam_id, api_key, force_refresh=True)
    
    # Atualiza usuário
    user.steam_online = status['online']
    user.steam_current_game = status['game'] or ''
    user.steam_current_game_appid = status['appid'] if status['game'] else None
    user.steam_last_update = datetime.now().isoformat()

    _salvar_usuario_no_banco(user)
    _hydra_atualizar_status_local(user)
    
    print(f'[/steam/sync-agora] {user.email}: online={status["online"]}, game="{status["game"]}", appid={status["appid"]}')
    
    return jsonify({
        'online': user.steam_online,
        'jogo': user.steam_current_game,
        'appid': user.steam_current_game_appid,
        'atualizado_em': user.steam_last_update,
        'hydra_jogo': user.hydra_current_game,
        'hydra_atualizado_em': user.hydra_last_update,
    })

@app.route('/steam/status/sincronizar', methods=['POST'])
def sincronizar_status_steam_endpoint():
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'erro': 'Não autenticado'}), 401

    try:
        sincronizar_status_steam(meu_email)
        user = USUARIOS_DB.get(_normalizar_email(meu_email))
        if user:
            _hydra_atualizar_status_local(user)
            return jsonify({
                'sucesso': True,
                'status': user.obter_status_steam(),
                'online': user.steam_online,
                'jogo': user.steam_current_game,
                'atualizado_em': user.steam_last_update,
                'hydra_jogo': user.hydra_current_game,
                'hydra_atualizado_em': user.hydra_last_update,
            })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

    return jsonify({'erro': 'Usuário não encontrado'}), 404


@app.route('/steam/status/<email>')
def obter_status_steam_usuario(email):
    """Retorna o status da Steam de um usuário específico.
    
    🔴 CRÍTICO: SEMPRE valida contra estado REAL do sistema.
    Nunca confia apenas em dados armazenados.
    """
    email_normalizado = _normalizar_email(email)
    user = USUARIOS_DB.get(email_normalizado)

    if not user:
        return jsonify({'erro': 'Usuário não encontrado'}), 404

    # PASSO 1: Sincronizar Steam
    try:
        if getattr(user, 'steam_id64', ''):
            sincronizar_status_steam(user.email)
    except Exception as e:
        print(f'[Steam Status] Erro ao sincronizar Steam: {e}')

    # PASSO 2: Para o usuário logado, fazer validação PROFUNDA do Hydra
    is_current_user = email_normalizado == _normalizar_email(session.get('user_email'))
    if is_current_user:
        print(f'\n[Status Endpoint] Usuário logado: {email_normalizado}')
        print(f'[Status Endpoint] Fazendo validação PROFUNDA do estado real...')
        
        # VALIDAÇÃO PROFUNDA - SEMPRE
        _hydra_sincronizar_estado_real(user)
        
        # Recarrega usuário para pegar dados atualizados
        user = USUARIOS_DB.get(email_normalizado)

    # PASSO 3: Montar resposta com estado validado
    # Para usuário logado, sempre revalida Hydra
    hydra_connected = False
    if is_current_user:
        estado_real = _hydra_get_full_state_real()
        hydra_connected = estado_real['hydra_ativo']
        
        print(f'[Status Endpoint] Estado real Hydra:')
        print(f'[Status Endpoint]   Ativo: {hydra_connected}')
        print(f'[Status Endpoint]   Jogo: "{estado_real["jogo"]}"')
        print(f'[Status Endpoint]   DB agora tem: "{user.hydra_current_game}"')

    online_status = bool(
        user.steam_online
        or user.hydra_current_game
        or hydra_connected
    )

    return jsonify({
        'email': user.email,
        'nome': user.nome,
        'status': user.obter_status_geral(),
        'steam_status': user.obter_status_steam(),
        'hydra_status': user.obter_status_hydra(),
        'online': online_status,
        'jogo': user.steam_current_game,
        'appid': user.steam_current_game_appid,
        'atualizado_em': user.steam_last_update,
        'hydra_connected': hydra_connected,
        'hydra_jogo': user.hydra_current_game,
        'hydra_atualizado_em': user.hydra_last_update,
    })

@app.route('/steam/test')
def steam_test():
    """Teste simples de conexão com Steam"""
    meu_email = session.get('user_email')
    if not meu_email:
        return "Não autenticado", 401
    
    user = USUARIOS_DB.get(_normalizar_email(meu_email))
    if not user:
        return "Usuário não encontrado", 404
    
    resultado = f"""
    <h2>🔧 Teste Steam</h2>
    <p><strong>Email:</strong> {user.email}</p>
    <p><strong>Steam ID64:</strong> {user.steam_id64 or 'NÃO CONFIGURADA'}</p>
    <p><strong>Steam online:</strong> {user.steam_online}</p>
    <p><strong>Steam current_game:</strong> {user.steam_current_game}</p>
    <p><strong>Steam appid:</strong> {user.steam_current_game_appid}</p>
    <p><strong>Steam last_update:</strong> {user.steam_last_update}</p>
    
    <hr>
    <h3>Status Parseado:</h3>
    <p>{user.obter_status_steam()}</p>
    
    <hr>
    <h3>Ações:</h3>
    <form method="POST" action="/steam/status/sincronizar" style="margin: 10px 0;">
        <button type="submit" style="padding: 10px 20px; font-size: 16px;">🔄 Sincronizar Agora</button>
    </form>
    
    <a href="/steam/debug/status" style="display: inline-block; margin: 10px 0; padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 5px;">
        📊 Ver JSON Debug
    </a>
    """
    return resultado, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/steam/debug/status')
def debug_status_steam():
    """Endpoint de debug para testar o status da Steam do usuário logado."""
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'erro': 'Não autenticado'}), 401
    
    user = USUARIOS_DB.get(_normalizar_email(meu_email))
    if not user:
        return jsonify({'erro': 'Usuário não encontrado'}), 404
    
    steam_id = _steam_id_ou_vanity_usuario(user)
    api_key = _steam_api_key_usuario(user)
    
    # Resolve Steam ID se for vanity URL
    if steam_id and not steam_id.isdigit():
        steam_id = _steam_resolver_steamid(steam_id, api_key) or steam_id
    
    if not steam_id:
        return jsonify({'erro': 'Steam ID não configurada'}), 400
    
    resultado = {
        'steam_id': steam_id,
        'has_api_key': bool(api_key),
        'status': _buscar_status_steam_usuario(steam_id, api_key, force_refresh=True),
        'requerimentos': {
            'perfil_publico': 'Seu perfil Steam precisa estar PÚBLICO',
            'visibilidade_jogo': 'A visibilidade de "Jogo em progresso" precisa estar PÚBLICA',
            'api_key': 'Uma Steam API Key melhora muito a detecção (opcional)',
        }
    }
    
    return jsonify(resultado)

@app.route('/steam/debug/resposta-bruta')
def debug_resposta_bruta_steam():
    """Mostra a resposta bruta da Steam para debug."""
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'erro': 'Não autenticado'}), 401
    
    user = USUARIOS_DB.get(_normalizar_email(meu_email))
    if not user:
        return jsonify({'erro': 'Usuário não encontrado'}), 404
    
    steam_id = _steam_id_ou_vanity_usuario(user)
    api_key = _steam_api_key_usuario(user)
    
    if steam_id and not steam_id.isdigit():
        steam_id = _steam_resolver_steamid(steam_id, api_key) or steam_id
    
    if not steam_id:
        return jsonify({'erro': 'Steam ID não configurada'}), 400
    
    # Testa conexão com a API
    resultado_api = {}
    if api_key:
        try:
            timestamp = f'&_t={int(time())}'
            url = (
                'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?'
                f'key={quote(api_key)}&steamids={quote(steam_id)}&format=json{timestamp}'
            )
            dados = _steam_fetch_json(url)
            players = dados.get('response', {}).get('players', [])
            if players:
                resultado_api = {
                    'sucesso': True,
                    'player': players[0],
                    'url': url[:50] + '...'
                }
            else:
                resultado_api = {'sucesso': False, 'erro': 'Nenhum jogador encontrado'}
        except Exception as e:
            resultado_api = {'sucesso': False, 'erro': str(e)}
    
    # Testa conexão com XML
    resultado_xml = {}
    try:
        if steam_id.isdigit():
            url = f'https://steamcommunity.com/profiles/{steam_id}/?xml=1&_t={int(time())}'
        else:
            url = f'https://steamcommunity.com/id/{quote(steam_id)}/?xml=1&_t={int(time())}'
        xml_texto = _steam_fetch_text(url)
        if xml_texto and len(xml_texto) > 100:
            raiz = ET.fromstring(xml_texto)
            resultado_xml = {
                'sucesso': True,
                'gameExtraInfo': raiz.findtext('gameExtraInfo'),
                'stateMessage': raiz.findtext('stateMessage'),
                'onlineState': raiz.findtext('onlineState'),
                'gameName': raiz.findtext('gameName'),
                'url': url[:50] + '...'
            }
        else:
            resultado_xml = {'sucesso': False, 'erro': 'Resposta vazia ou muito curta'}
    except Exception as e:
        resultado_xml = {'sucesso': False, 'erro': str(e)}
    
    return jsonify({
        'steam_id': steam_id,
        'api_key_presente': bool(api_key),
        'api_resposta': resultado_api,
        'xml_resposta': resultado_xml,
        'status_processado': _buscar_status_steam_usuario(steam_id, api_key, force_refresh=True)
    })

@app.route('/discord/abrir')
def abrir_discord():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(session['user_email'])
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))

    if not user.discord_server:
        flash("JITS CALL não configurado no seu perfil.", "warning")
        return redirect(url_for('perfil', email=user.email))

    user.discord_online = True
    link_discord = user.obter_link_discord()
    if link_discord:
        return redirect(link_discord)

    flash("Não foi possível abrir o Discord. Verifique o link no seu perfil.", "danger")
    return redirect(url_for('perfil', email=user.email))


def _normalizar_servidor_discord(texto: str) -> str:
    texto = (texto or '').strip()
    if not texto:
        return 'Geral'
    if 'discord.gg/' in texto:
        texto = texto.split('discord.gg/', 1)[1]
    elif 'discord.com/invite/' in texto:
        texto = texto.split('discord.com/invite/', 1)[1]
    return texto.rstrip('/').strip() or 'Geral'


def _slug_servidor_discord(texto: str) -> str:
    texto = _normalizar_servidor_discord(texto)
    slug = re.sub(r'[^a-z0-9]+', '-', texto.lower()).strip('-')
    return slug or 'geral'


@app.route('/discord/call')
def discord_call():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('dashboard'))

    servidor = _normalizar_servidor_discord(request.args.get('servidor', '') or user.discord_server or 'Geral')
    room_slug = _slug_servidor_discord(servidor)
    room_name = f'gamelink-{room_slug}'
    convite_url = url_for('discord_call', servidor=servidor, _external=True)

    user.discord_online = True
    _registrar_presenca_call(user.email, room_slug)

    servidores_recomendados = []
    vistos = set()
    for usuario in USUARIOS_DB.values():
        servidor_usuario = _normalizar_servidor_discord(usuario.discord_server)
        if not servidor_usuario or servidor_usuario == 'Geral':
            continue
        slug_usuario = _slug_servidor_discord(servidor_usuario)
        if slug_usuario in vistos:
            continue
        vistos.add(slug_usuario)
        servidores_recomendados.append({
            'nome': servidor_usuario,
            'slug': slug_usuario,
            'convite': url_for('discord_call', servidor=servidor_usuario),
        })

    servidores_recomendados.sort(key=lambda item: item['nome'].lower())
    participantes = [
        usuario for usuario in USUARIOS_DB.values()
        if _slug_servidor_discord(_normalizar_servidor_discord(usuario.discord_server)) == room_slug
    ]
    status_call = _serializar_status_call(room_slug)

    return render_template(
        'discord_call.html',
        usuario=user,
        servidor=servidor,
        room_name=room_name,
        room_slug=room_slug,
        convite_url=convite_url,
        servidores_recomendados=servidores_recomendados,
        participantes=participantes,
        participantes_ativos=status_call['participantes_ativos'],
        quantidade_participantes=status_call['quantidade'],
        call_iniciada_em=status_call['call_iniciada_em'],
        tempo_decorrido=status_call['tempo_decorrido'],
    )


@app.route('/discord/call/status')
def discord_call_status():
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'ok': False, 'error': 'not_logged_in'}), 401

    servidor = _normalizar_servidor_discord(request.args.get('servidor', '') or 'Geral')
    room_slug = _slug_servidor_discord(servidor)
    status_call = _serializar_status_call(room_slug)
    return jsonify({'ok': True, **status_call})


@app.route('/discord/call/presenca', methods=['POST'])
def discord_call_presenca():
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'ok': False, 'error': 'not_logged_in'}), 401

    dados = request.get_json(silent=True) or {}
    room_slug = _slug_servidor_discord(dados.get('room_slug') or 'geral')
    _registrar_presenca_call(meu_email, room_slug)

    user = USUARIOS_DB.get(meu_email)
    if user:
        user.discord_online = True

    return jsonify({'ok': True})


@app.route('/discord/call/sair', methods=['POST'])
def discord_call_sair():
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'ok': False, 'error': 'not_logged_in'}), 401

    _remover_presenca_call(meu_email)
    user = USUARIOS_DB.get(meu_email)
    if user:
        user.discord_online = False

    return jsonify({'ok': True})

@app.route('/conversa/<email_amigo>')
def conversa(email_amigo):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))
    if not GerenciadorAmigos.sao_amigos(meu_email, email_amigo):
        flash("Você só pode conversar com amigos.", "danger")
        return redirect(url_for('perfil', email=email_amigo))

    amigo = USUARIOS_DB.get(email_amigo)
    if not amigo:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))

    mensagens = GerenciadorMensagens.obter_conversa(meu_email, email_amigo)
    return render_template('conversa.html', amigo=amigo, mensagens=mensagens, usuarios=USUARIOS_DB)

@app.route('/conversa/<email_destino>/enviar', methods=['POST'])
def enviar_mensagem(email_destino):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))
    if not GerenciadorAmigos.sao_amigos(meu_email, email_destino):
        flash("Você só pode enviar mensagens para amigos.", "danger")
        return redirect(url_for('perfil', email=email_destino))

    conteudo = request.form.get('conteudo', '').strip()
    if not conteudo:
        flash("Mensagem não pode ser vazia.", "danger")
        return redirect(url_for('conversa', email_amigo=email_destino))

    novo_id = max([m.id for m in MENSAGENS_DB], default=0) + 1
    mensagem = GerenciadorMensagens.enviar_mensagem(novo_id, meu_email, email_destino, conteudo)
    persistir_mensagem(mensagem)

    todas_notifs = [n for lista in NOTIFICACOES_DB.values() for n in lista]
    id_notif = max([n.id for n in todas_notifs], default=0) + 1
    remetente = USUARIOS_DB.get(meu_email)
    GerenciadorNotificacoes.criar_notificacao(
        id_notif=id_notif,
        email_receptor=email_destino,
        tipo='mensagem',
        titulo='💬 Nova mensagem recebida',
        descricao=f'{remetente.nome if remetente else meu_email} enviou uma nova mensagem para você.',
        link=f'/conversa/{meu_email}'
    )
    for notif in NOTIFICACOES_DB.get(email_destino, []):
        if notif.id == id_notif:
            persistir_notificacao(notif)
            break

    flash("Mensagem enviada!", "success")
    return redirect(url_for('conversa', email_amigo=email_destino))

@app.route('/amizade/adicionar/<email_alvo>')
def adicionar_amigo(email_alvo):
    meu_email = session.get('user_email')
    email_alvo = _normalizar_email(email_alvo)
    if not meu_email or meu_email == email_alvo:
        return redirect(url_for('dashboard'))
    try:
        # 1. Envia a solicitação de amizade
        id_solicitacao = max([s.id for s in AMIZADES_DB.values()], default=0) + 1
        amizade = GerenciadorAmigos.enviar_solicitacao(id_solicitacao, meu_email, email_alvo)
        persistir_amizade(amizade)
        
        # Criamos um ID incremental para a notificação buscar de todas as listas de usuários
        todas_notifs = [n for lista in NOTIFICACOES_DB.values() for n in lista]
        id_notif = max([n.id for n in todas_notifs], default=0) + 1
        
        GerenciadorNotificacoes.criar_notificacao(
            id_notif=id_notif,
            email_receptor=email_alvo,       # Quem recebe é o alvo
            tipo='amizade',                  # Tipo esperado pelo seu html
            titulo='👥 Nova Solicitação de Amizade!',
            descricao=f'{meu_email} enviou um pedido de amizade para você.',
            link=f'/amizade/aceitar/{meu_email}' # Link direto para aceitar a solicitação
        )
        for notif in NOTIFICACOES_DB.get(email_alvo, []):
            if notif.id == id_notif:
                persistir_notificacao(notif)
                break

        flash("Solicitação de amizade enviada!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_alvo))

@app.route('/amizade/aceitar/<email_amigo>')
def aceitar_amizade(email_amigo):
    meu_email = session.get('user_email')
    email_amigo = _normalizar_email(email_amigo)
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.aceitar_solicitacao(meu_email, email_amigo)
        chave = f"{min(meu_email, email_amigo)}_{max(meu_email, email_amigo)}"
        if chave in AMIZADES_DB:
            persistir_amizade(AMIZADES_DB[chave])
        
        # Criação correta do Objeto de Notificação
        todas_notifs = [n for lista in NOTIFICACOES_DB.values() for n in lista]
        id_notif = max([n.id for n in todas_notifs], default=0) + 1
        
        GerenciadorNotificacoes.criar_notificacao(
            id_notif=id_notif,
            email_receptor=email_amigo,
            tipo='amizade',
            titulo='🤝 Solicitação Aceita!',
            descricao=f'{session.get("user_nome")} aceitou o seu pedido de amizade. Agora vocês são amigos!',
            link=f'/perfil/{meu_email}'
        )
        for notif in NOTIFICACOES_DB.get(email_amigo, []):
            if notif.id == id_notif:
                persistir_notificacao(notif)
                break

        flash("Amizade aceita!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_amigo)) # Redireciona de volta para o perfil do seu novo amigo

@app.route('/amizade/recusar/<email_amigo>')
def recusar_amizade(email_amigo):
    meu_email = session.get('user_email')
    email_amigo = _normalizar_email(email_amigo)
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.recusar_solicitacao(meu_email, email_amigo)
        chave = f"{min(meu_email, email_amigo)}_{max(meu_email, email_amigo)}"
        if chave in AMIZADES_DB:
            persistir_amizade(AMIZADES_DB[chave])
        flash("Solicitação recusada!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_amigo)) #Mantém no perfil

@app.route('/amizade/remover/<email_amigo>')
def remover_amigo(email_amigo):
    meu_email = session.get('user_email')
    email_amigo = _normalizar_email(email_amigo)
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.recusar_solicitacao(meu_email, email_amigo)
        remover_amizade(meu_email, email_amigo)
        flash("Amigo removido!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_amigo)) 

# --- Rotas de Biblioteca Pessoal ---
@app.route('/biblioteca/adicionar/<int:jogo_id>')
def adicionar_biblioteca(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        id_biblioteca = max([b.id for b in BIBLIOTECA_DB.values()], default=0) + 1
        item = GerenciadorBiblioteca.adicionar_jogo(id_biblioteca, meu_email, jogo_id)
        persistir_biblioteca_item(item)
        flash("Jogo adicionado à biblioteca!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('dashboard', foco='biblioteca'))

@app.route('/biblioteca/remover/<int:jogo_id>')
def remover_biblioteca(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorBiblioteca.remover_jogo(meu_email, jogo_id)
        remover_biblioteca_item(meu_email, jogo_id)
        flash("Jogo removido da biblioteca!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/biblioteca/avaliar/<int:jogo_id>', methods=['POST'])
def avaliar_biblioteca(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))
    nota = request.form.get('nota', '0.0')
    comentario = request.form.get('comentario', '').strip()
    try:
        nota = float(nota)
        item = GerenciadorBiblioteca.atualizar_avaliacao(meu_email, jogo_id, nota, comentario)
        persistir_biblioteca_item(item)
        if comentario:
            flash(f"Avaliação atualizada para {nota:.1f} estrelas com comentário!", "success")
        else:
            flash(f"Avaliação atualizada para {nota:.1f} estrelas!", "success")
    except Exception as e:
        flash(f"Erro ao avaliar: {str(e)}", "danger")
    return redirect(request.referrer or url_for('biblioteca'))


@app.route('/steam/importar-biblioteca', methods=['POST'])
def importar_biblioteca_steam():
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    user = USUARIOS_DB.get(meu_email)
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('biblioteca'))

    jogos_importados, jogos_ja_existiam, erro_steam = importar_steam_para_biblioteca_local(meu_email)

    if jogos_importados:
        flash(f'{jogos_importados} jogo(s) da Steam foram importados para sua biblioteca local.', 'success')
    elif jogos_ja_existiam:
        flash('Sua biblioteca local já tinha os jogos da Steam importados.', 'info')
    elif erro_steam:
        flash(erro_steam, 'warning')
    else:
        flash('Nenhum jogo da Steam foi importado.', 'warning')

    return redirect(request.referrer or url_for('biblioteca'))

@app.route('/biblioteca')
def minha_biblioteca():
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    biblioteca_cards = montar_biblioteca_cards(meu_email)
    steam_contexto = montar_steam_contexto(USUARIOS_DB.get(meu_email))
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
        return render_template('_biblioteca_conteudo.html', biblioteca_cards=biblioteca_cards, jogos=JOGOS_DB, usuarios=USUARIOS_DB, steam_contexto=steam_contexto)
    return render_template('biblioteca.html', biblioteca_cards=biblioteca_cards, jogos=JOGOS_DB, usuarios=USUARIOS_DB, steam_contexto=steam_contexto)

# --- Rotas de Reviews ---
@app.route('/jogo/<int:jogo_id>/review/novo', methods=['POST'])
def novo_review(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    if jogo_id not in JOGOS_DB:
        flash("Jogo não encontrado!", "danger")
        return redirect(url_for('dashboard'))
    if not GerenciadorBiblioteca.jogo_na_biblioteca(meu_email, jogo_id):
        flash("Você precisa adicionar o jogo à biblioteca primeiro!", "danger")
        return redirect(url_for('dashboard'))
    
    titulo = request.form.get('titulo', '').strip()
    conteudo = request.form.get('conteudo', '').strip()
    nota = request.form.get('nota', '5.0')
    
    try:
        nota = float(nota)
        res = moderate_text(titulo)
        res_c = moderate_text(conteudo)
        if not res.get('allowed', True) or not res_c.get('allowed', True):
            flash("Seu review contém conteúdo impróprio!", "danger")
            return redirect(url_for('perfil', email=meu_email))
        
        if not titulo or not conteudo:
            flash("Título e conteúdo são obrigatórios!", "danger")
            return redirect(url_for('perfil', email=meu_email))
        
        if nota < 0 or nota > 5:
            raise ValueError("A nota precisa estar entre 0.0 e 5.0")

        id_review = max(REVIEWS_DB.keys(), default=0) + 1
        review = GerenciadorReviews.criar_review(id_review, jogo_id, meu_email, titulo, conteudo, nota)
        persistir_review(review)
        flash("Review publicado com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao criar review: {str(e)}", "danger")
    return redirect(url_for('perfil', email=meu_email))

@app.route('/review/<int:review_id>/deletar', methods=['POST'])
def deletar_review(review_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    review = REVIEWS_DB.get(review_id)
    if not review or (review.email_usuario != meu_email and not session.get('is_admin')):
        flash("Não tem permissão para deletar este review!", "danger")
        return redirect(url_for('dashboard'))
    try:
        GerenciadorReviews.deletar_review(review_id)
        marcar_review_visivel(review_id, False)
        flash("Review deletado!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/review/<int:review_id>/curtir', methods=['POST'])
def curtir_review(review_id):
    review = REVIEWS_DB.get(review_id)
    if not review:
        return jsonify({'erro': 'Review não encontrado'}), 404
    review.adicionar_curtida()
    persistir_review(review)
    return jsonify({'curtidas': review.curtidas})

@app.route('/review/<int:review_id>/comentar', methods=['POST'])
def comentar_review(review_id):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    review = REVIEWS_DB.get(review_id)
    if not review or not review.visivel:
        flash('Review não encontrada.', 'danger')
        return redirect(url_for('dashboard'))

    texto = request.form.get('texto', '').strip()
    if not texto:
        flash('Comentário não pode estar vazio!', 'danger')
        return redirect(request.referrer or url_for('perfil', email=review.email_usuario))

    resultado = moderate_text(texto)
    if not resultado.get('allowed', True):
        flash('Comentário contém termos impróprios!', 'danger')
        return redirect(request.referrer or url_for('perfil', email=review.email_usuario))

    try:
        novo_id = max([c.id for c in REVIEW_COMENTARIOS_DB], default=0) + 1
        comentario = GerenciadorReviews.adicionar_comentario_review(novo_id, review_id, meu_email, texto)
        persistir_review_comentario(comentario)
        flash('Comentário adicionado na review!', 'success')
    except Exception as e:
        flash(f'Erro ao comentar review: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('perfil', email=review.email_usuario))

@app.route('/review/comentario/<int:comentario_id>/deletar', methods=['POST'])
def deletar_comentario_review(comentario_id):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))

    comentario = next((c for c in REVIEW_COMENTARIOS_DB if c.id == comentario_id), None)
    if not comentario:
        flash('Comentário não encontrado.', 'danger')
        return redirect(url_for('dashboard'))

    if comentario.email_usuario != meu_email and not session.get('is_admin'):
        flash('Sem permissão para deletar este comentário.', 'danger')
        return redirect(request.referrer or url_for('perfil', email=REVIEWS_DB[comentario.review_id].email_usuario if comentario.review_id in REVIEWS_DB else meu_email))

    try:
        GerenciadorReviews.deletar_comentario_review(comentario_id)
        marcar_review_comentario_visivel(comentario_id, False)
        flash('Comentário deletado!', 'info')
    except Exception as e:
        flash(str(e), 'danger')

    review = REVIEWS_DB.get(comentario.review_id)
    return redirect(request.referrer or url_for('perfil', email=review.email_usuario if review else meu_email))

# --- Rotas de Notificações ---
@app.route('/notificacoes')
def notificacoes():
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    notif_list = GerenciadorNotificacoes.obter_notificacoes(meu_email)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
        return render_template('_notificacoes_conteudo.html', notificacoes=notif_list, usuarios=USUARIOS_DB)
    
    # Se o usuário acessou digitando a URL no navegador, entrega a página completa:
    return render_template('notificacoes.html', notificacoes=notif_list, usuarios=USUARIOS_DB)

@app.route('/notificacao/<int:notif_id>/marcar-lida', methods=['POST'])
def marcar_notif_lida(notif_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return jsonify({'erro': 'Não logado'}), 401
    try:
        GerenciadorNotificacoes.marcar_como_lida(meu_email, notif_id)
        marcar_notificacao_lida(meu_email, notif_id)
        return jsonify({'sucesso': True})
    except Exception as e:
        return jsonify({'erro': str(e)}), 400


@app.route('/mensagens/nao-lidas/contador')
def contador_mensagens_nao_lidas():
    meu_email = session.get('user_email')
    if not meu_email:
        return jsonify({'count': 0})

    count = GerenciadorNotificacoes.contar_nao_lidas_por_tipo(meu_email, 'mensagem')
    return jsonify({'count': count})

# --- Rotas para Posts ---
@app.route('/posts/novo', methods=['POST'])
def novo_post():
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    
    titulo = request.form.get('titulo', '').strip()
    conteudo = request.form.get('conteudo', '').strip()
    
    if not titulo or not conteudo:
        flash("Título e conteúdo são obrigatórios!", "danger")
        return redirect(url_for('dashboard'))
    
    res_t = moderate_text(titulo)
    res_c = moderate_text(conteudo)
    if not res_t.get('allowed', True) or not res_c.get('allowed', True):
        flash("Conteúdo contém termos impróprios!", "danger")
        return redirect(url_for('dashboard'))
    
    imagem_url = None
    if 'imagem' in request.files:
        file = request.files['imagem']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"{session['user_email']}_{int(datetime.now().timestamp())}_{file.filename}")
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagem_url = f"/static/uploads/{filename}"
    
    novo_id = max(POSTS_DB.keys(), default=0) + 1
    novo_post_obj = Post(novo_id, session['user_email'], titulo, conteudo, imagem_url)
    POSTS_DB[novo_id] = novo_post_obj
    persistir_post(novo_post_obj)
    
    # Sistema de Notificações Ativas
    amigos = GerenciadorAmigos.obter_amigos(session['user_email'])
    user_atual = USUARIOS_DB.get(session['user_email'])
    nome_autor = user_atual.nome if user_atual else session['user_email']
    
    for email_amigo in amigos:
        id_notif = max([n.id for notifs in NOTIFICACOES_DB.values() for n in notifs], default=0) + 1
        GerenciadorNotificacoes.notificar_novo_post(
            email_amigo,
            f"Novo post de {nome_autor}",
            f"{nome_autor} postou: {titulo[:50]}...",
            novo_id,
            id_notif
        )
        for notif in NOTIFICACOES_DB.get(email_amigo, []):
            if notif.id == id_notif:
                persistir_notificacao(notif)
                break
    
    flash("Post criado com sucesso!", "success")
    return redirect(url_for('dashboard'))

@app.route('/posts/<int:post_id>')
def ver_post(post_id):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    post = POSTS_DB.get(post_id)
    if not post or not post.visivel:
        flash("Post não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    
    comentarios = [c for c in COMENTARIOS_POSTS_DB if c.post_id == post_id and c.visivel]
    autor = USUARIOS_DB.get(post.autor_email)
    return render_template('ver_post.html', post=post, comentarios=comentarios, autor=autor, usuarios=USUARIOS_DB)

@app.route('/posts/<int:post_id>/curtir', methods=['POST'])
def curtir_post(post_id):
    if 'user_email' not in session: 
        return jsonify({'error': 'Não logado'}), 401
    post = POSTS_DB.get(post_id)
    if not post:
        return jsonify({'error': 'Post não encontrado'}), 404
    
    email = session['user_email']
    curtiu = False if post.usuario_curtiu(email) else True
    post.descurtir(email) if post.usuario_curtiu(email) else post.curtir(email)
    persistir_post_like(post_id, email, curtiu)
    
    return jsonify({'curtiu': curtiu, 'total_curtidas': post.get_total_curtidas()})

@app.route('/posts/<int:post_id>/comentar', methods=['POST'])
def comentar_post(post_id):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    post = POSTS_DB.get(post_id)
    if not post or not post.visivel:
        flash("Post não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    
    texto = request.form.get('texto', '').strip()
    if not texto:
        flash("Comentário não pode estar vazio!", "danger")
        return redirect(url_for('ver_post', post_id=post_id))
    
    res = moderate_text(texto)
    if not res.get('allowed', True):
        flash("Comentário contém termos impróprios!", "danger")
        return redirect(url_for('ver_post', post_id=post_id))
    
    novo_id = len(COMENTARIOS_POSTS_DB) + 1
    comentario = Comentario(novo_id, post_id, session['user_email'], texto)
    COMENTARIOS_POSTS_DB.append(comentario)
    post.adicionar_comentario(novo_id)
    persistir_comentario_post(comentario)
    
    flash("Comentário adicionado com sucesso!", "success")
    return redirect(url_for('ver_post', post_id=post_id))

@app.route('/posts/<int:post_id>/deletar', methods=['POST'])
def deletar_post(post_id):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    post = POSTS_DB.get(post_id)
    if not post:
        flash("Post não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    
    if session['user_email'] != post.autor_email and not session.get('is_admin'):
        flash("Sem permissão para deletar.", "danger")
        return redirect(url_for('ver_post', post_id=post_id))
    
    post.visivel = False
    marcar_post_visivel(post_id, False)
    flash("Post deletado!", "success")
    return redirect(url_for('dashboard'))

@app.route('/comentario/<int:comentario_id>/deletar', methods=['POST'])
def deletar_comentario_post(comentario_id):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    comentario = next((c for c in COMENTARIOS_POSTS_DB if c.id == comentario_id), None)
    if not comentario:
        flash("Comentário não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    
    if session['user_email'] != comentario.autor_email and not session.get('is_admin'):
        flash("Sem permissão.", "danger")
        return redirect(url_for('ver_post', post_id=comentario.post_id))
    
    comentario.visivel = False
    marcar_comentario_post_visivel(comentario_id, False)
    flash("Comentário deletado!", "success")
    return redirect(url_for('ver_post', post_id=comentario.post_id))

@app.route('/moderacao/posts')
def painel_moderacao_posts():
    if not session.get('is_admin'): 
        return redirect(url_for('dashboard'))
    posts_ocultos = {k: v for k, v in POSTS_DB.items() if not v.visivel}
    comentarios_ocultos = [c for c in COMENTARIOS_POSTS_DB if not c.visivel]
    return render_template('painel_moderacao.html', posts_ocultos=posts_ocultos, comentarios_ocultos=comentarios_ocultos, usuarios=USUARIOS_DB)

@app.route('/moderacao/post/<int:post_id>/restaurar', methods=['POST'])
def restaurar_post(post_id):
    if not session.get('is_admin'): 
        return redirect(url_for('dashboard'))
    post = POSTS_DB.get(post_id)
    if post:
        post.visivel = True
        flash("Post restaurado!", "success")
    return redirect(url_for('painel_moderacao_posts'))

@app.route('/logout')
def logout():
    email = session.get('user_email')
    if email in ONLINE_USERS:
        ONLINE_USERS.discard(email)
    _remover_presenca_call(email)
    user = USUARIOS_DB.get(email)
    if user:
        user.discord_online = False
    session.clear()
    return redirect(url_for('login'))

# --- Rotas de API para AJAX ---
@app.route('/api/reviews/usuario/<email>')
def api_reviews_usuario(email):
    reviews = GerenciadorReviews.obter_reviews_usuario(email)
    reviews_data = []
    for review in reviews:
        jogo = JOGOS_DB.get(review.jogo_id)
        comentarios = GerenciadorReviews.obter_comentarios_review(review.id)
        reviews_data.append({
            'id': review.id,
            'titulo': review.titulo,
            'conteudo': review.conteudo,
            'nota': review.nota,
            'jogo_titulo': jogo.titulo if jogo else f"Jogo #{review.jogo_id}",
            'data': review.data_criacao.strftime('%d/%m/%Y'),
            'total_comentarios': len(comentarios),
            'comentarios': [
                {
                    'id': comentario.id,
                    'autor_email': comentario.email_usuario,
                    'autor_nome': USUARIOS_DB.get(comentario.email_usuario).nome if USUARIOS_DB.get(comentario.email_usuario) else comentario.email_usuario,
                    'texto': comentario.texto,
                    'data': comentario.data_criacao.strftime('%d/%m/%Y %H:%M')
                }
                for comentario in comentarios
            ]
        })
    return jsonify({'reviews': reviews_data})

@app.route('/api/biblioteca/<email>')
def api_biblioteca(email):
    if email != session.get('user_email'):
        return jsonify({'erro': 'Acesso negado'}), 403
    biblioteca = GerenciadorBiblioteca.obter_biblioteca(email)
    items = []
    for item in biblioteca:
        jogo = JOGOS_DB.get(item.jogo_id)
        items.append({
            'id': item.id,
            'jogo_id': item.jogo_id,
            'jogo_titulo': jogo.titulo if jogo else f"Jogo #{item.jogo_id}",
            'data_adicao': item.data_adicao.strftime('%d/%m/%Y'),
            'tempo_jogado': item.tempo_jogado_horas,
            'concluido': item.concluido,
            'platinado': item.platinado
        })
    return jsonify({'biblioteca': items})

@app.route('/api/amigos/<email>')
def api_amigos(email):
    amigos = GerenciadorAmigos.obter_amigos(email)
    amigos_data = []
    for amigo_email in amigos:
        user = USUARIOS_DB.get(amigo_email)
        if user:
            amigos_data.append({'email': amigo_email, 'nome': user.nome})
    return jsonify({'amigos': amigos_data})

from threading import Event, Thread
import webbrowser

try:
    import webview
except Exception as exc:
    webview = None
    WEBVIEW_IMPORT_ERROR = exc


def iniciar_flask():
    app.run(host=LOCAL_HOST, port=LOCAL_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    Thread(target=iniciar_flask, daemon=True).start()

    if webview is None:
        print(f'Webview indisponível: {WEBVIEW_IMPORT_ERROR}')
        print('Abrindo o navegador em vez disso...')
        webbrowser.open(f'{BASE_URL}/login')
    else:
        try:
            webview.create_window(
                'Gamer Link',
                f'{BASE_URL}/login',
                width=1400,
                height=900
            )
            webview.start()
        except Exception as exc:
            print(f'Não foi possível iniciar a janela desktop: {exc}')
            print('Abrindo o navegador em vez disso...')
            webbrowser.open(f'{BASE_URL}/login')

    try:
        Event().wait()
    except KeyboardInterrupt:
        print('Encerrando o servidor...')