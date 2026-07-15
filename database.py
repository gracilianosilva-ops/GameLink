import os
import json
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'gamelink.db')

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    token_recuperacao TEXT,
    idade INTEGER,
    gosto_jogos TEXT,
    telefone TEXT,
    steam_id64 TEXT,
    steam_api_key TEXT,
    hydra_account_email TEXT,
    hydra_usuario TEXT,
    hydra_pin TEXT,
    hydra_token TEXT,
    hydra_current_game TEXT,
    hydra_last_update TEXT,
    foto_perfil TEXT,
    data_cadastro TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    genero TEXT NOT NULL,
    desenvolvedora TEXT NOT NULL,
    ano INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jogo_categoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jogo_id INTEGER NOT NULL,
    categoria_id INTEGER NOT NULL,
    UNIQUE(jogo_id, categoria_id),
    FOREIGN KEY(jogo_id) REFERENCES jogos(id) ON DELETE CASCADE,
    FOREIGN KEY(categoria_id) REFERENCES categorias(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    autor_email TEXT NOT NULL,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    imagem_url TEXT,
    data_criacao TEXT NOT NULL,
    visivel INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(autor_email) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    autor_email TEXT NOT NULL,
    texto TEXT NOT NULL,
    data_criacao TEXT NOT NULL,
    visivel INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY(autor_email) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS amizades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_solicitante TEXT NOT NULL,
    email_receptor TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    data_solicitacao TEXT NOT NULL,
    data_aceito TEXT,
    UNIQUE(email_solicitante, email_receptor),
    FOREIGN KEY(email_solicitante) REFERENCES usuarios(email) ON DELETE CASCADE,
    FOREIGN KEY(email_receptor) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS biblioteca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_usuario TEXT NOT NULL,
    jogo_id INTEGER NOT NULL,
    data_adicao TEXT NOT NULL,
    tempo_jogado_horas INTEGER NOT NULL DEFAULT 0,
    concluido INTEGER NOT NULL DEFAULT 0,
    platinado INTEGER NOT NULL DEFAULT 0,
    UNIQUE(email_usuario, jogo_id),
    FOREIGN KEY(email_usuario) REFERENCES usuarios(email) ON DELETE CASCADE,
    FOREIGN KEY(jogo_id) REFERENCES jogos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jogo_id INTEGER NOT NULL,
    email_usuario TEXT NOT NULL,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    nota INTEGER NOT NULL,
    data_criacao TEXT NOT NULL,
    visivel INTEGER NOT NULL DEFAULT 1,
    curtidas INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(jogo_id) REFERENCES jogos(id) ON DELETE CASCADE,
    FOREIGN KEY(email_usuario) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    email_usuario TEXT NOT NULL,
    texto TEXT NOT NULL,
    data_criacao TEXT NOT NULL,
    visivel INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE,
    FOREIGN KEY(email_usuario) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notificacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_receptor TEXT NOT NULL,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    link TEXT,
    data_criacao TEXT NOT NULL,
    lida INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(email_receptor) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    email_usuario TEXT NOT NULL,
    UNIQUE(post_id, email_usuario),
    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY(email_usuario) REFERENCES usuarios(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_remetente TEXT NOT NULL,
    email_destino TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    data_envio TEXT NOT NULL,
    FOREIGN KEY(email_remetente) REFERENCES usuarios(email) ON DELETE CASCADE,
    FOREIGN KEY(email_destino) REFERENCES usuarios(email) ON DELETE CASCADE
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def _ensure_usuario_columns(conn):
    cursor = conn.cursor()
    cursor.execute('PRAGMA table_info(usuarios)')
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ('steam_id64', 'TEXT'),
        ('steam_api_key', 'TEXT'),
        ('steam_online', 'INTEGER'),
        ('steam_current_game', 'TEXT'),
        ('steam_current_game_appid', 'INTEGER'),
        ('steam_playtime_minutes', 'INTEGER'),
        ('steam_last_update', 'TEXT'),
        ('hydra_account_email', 'TEXT'),
        ('hydra_usuario', 'TEXT'),
        ('hydra_pin', 'TEXT'),
        ('hydra_token', 'TEXT'),
        ('hydra_current_game', 'TEXT'),
        ('hydra_last_update', 'TEXT'),
        ('foto_perfil', 'TEXT'),
        ('data_cadastro', 'TEXT'),
    ]

    for column_name, column_type in columns_to_add:
        if column_name not in existing_columns:
            cursor.execute(
                f'ALTER TABLE usuarios ADD COLUMN {column_name} {column_type}'
            )

    conn.commit()


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _ensure_usuario_columns(conn)
    conn.commit()
    conn.close()


def seed_initial_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM usuarios')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO usuarios (nome, email, password, is_admin) VALUES (?, ?, ?, ?)',
            ('Caxa', 'admin@gamelink.com', 'admin123', 1)
        )

    cursor.execute('SELECT COUNT(*) FROM categorias')
    if cursor.fetchone()[0] == 0:
        categorias = [('RPG',), ('Ação',)]
        cursor.executemany('INSERT INTO categorias (nome) VALUES (?)', categorias)

    cursor.execute('SELECT COUNT(*) FROM jogos')
    if cursor.fetchone()[0] == 0:
        jogos = [
            ('The Witcher 3', 'RPG', 'CD Projekt Red', 2015),
            ('Elden Ring', 'RPG', 'FromSoftware', 2022),
            ('GTA V', 'Ação', 'Rockstar', 2013),
        ]
        cursor.executemany(
            'INSERT INTO jogos (titulo, genero, desenvolvedora, ano) VALUES (?, ?, ?, ?)',
            jogos
        )

    conn.commit()
    conn.close()


def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    seed_initial_data()


def _dt_to_db(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat(sep=' ', timespec='seconds')


def _dt_from_db(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')


def carregar_estado_persistido():
    from modelos.usuario import USUARIOS_DB, Usuario, Admin
    from modelos.jogo import JOGOS_DB, Jogo, Categoria
    from modelos.posts import POSTS_DB, COMENTARIOS_POSTS_DB, Post, Comentario
    from modelos.amigos_biblioteca import (
        AMIZADES_DB, BIBLIOTECA_DB, REVIEWS_DB, REVIEW_COMENTARIOS_DB,
        NOTIFICACOES_DB, MENSAGENS_DB,
        SolicitacaoAmizade, BibliotecaJogo, Review, ComentarioReview,
        Notificacao, Mensagem,
    )

    conn = get_connection()
    cursor = conn.cursor()

    USUARIOS_DB.clear()
    JOGOS_DB.clear()
    POSTS_DB.clear()
    COMENTARIOS_POSTS_DB.clear()
    AMIZADES_DB.clear()
    BIBLIOTECA_DB.clear()
    REVIEWS_DB.clear()
    REVIEW_COMENTARIOS_DB.clear()
    NOTIFICACOES_DB.clear()
    MENSAGENS_DB.clear()

    cursor.execute('SELECT * FROM usuarios ORDER BY id ASC')
    for row in cursor.fetchall():
        usuario = Admin(row['id'], row['nome'], row['email'], row['password']) if row['is_admin'] else Usuario(row['id'], row['nome'], row['email'], row['password'])
        usuario.token_recuperacao = row['token_recuperacao']
        usuario.idade = row['idade']
        usuario.gosto_jogos = row['gosto_jogos'] or ''
        usuario.telefone = row['telefone'] or ''
        usuario.steam_id64 = row['steam_id64'] or ''
        usuario.steam_api_key = row['steam_api_key'] or ''
        usuario.hydra_account_email = row['hydra_account_email'] or ''
        usuario.hydra_usuario = row['hydra_usuario'] or ''
        usuario.hydra_pin = row['hydra_pin'] or ''
        usuario.hydra_token = row['hydra_token'] or ''
        usuario.foto_perfil = row['foto_perfil'] or ''
        usuario.data_cadastro = row['data_cadastro'] or None
        if not usuario.data_cadastro:
            usuario.data_cadastro = datetime.now().isoformat(timespec='seconds')
        USUARIOS_DB[usuario.email.lower()] = usuario

    cursor.execute('SELECT * FROM categorias ORDER BY id ASC')
    categorias_db = {row['id']: Categoria(row['id'], row['nome']) for row in cursor.fetchall()}

    cursor.execute('SELECT * FROM jogos ORDER BY id ASC')
    for row in cursor.fetchall():
        jogo = Jogo(row['id'], row['titulo'], row['genero'], row['desenvolvedora'], row['ano'])
        JOGOS_DB[jogo.id] = jogo

    cursor.execute('SELECT jogo_id, categoria_id FROM jogo_categoria ORDER BY id ASC')
    for row in cursor.fetchall():
        jogo = JOGOS_DB.get(row['jogo_id'])
        categoria = categorias_db.get(row['categoria_id'])
        if jogo and categoria:
            try:
                jogo.associar_categoria(categoria)
            except Exception:
                pass

    cursor.execute('SELECT * FROM posts ORDER BY id ASC')
    for row in cursor.fetchall():
        post = Post(row['id'], row['autor_email'], row['titulo'], row['conteudo'], row['imagem_url'])
        post.data_criacao = _dt_from_db(row['data_criacao']) or post.data_criacao
        post.visivel = bool(row['visivel'])
        POSTS_DB[post.id] = post

    cursor.execute('SELECT * FROM comentarios ORDER BY id ASC')
    for row in cursor.fetchall():
        comentario = Comentario(row['id'], row['post_id'], row['autor_email'], row['texto'])
        comentario.data_criacao = _dt_from_db(row['data_criacao']) or comentario.data_criacao
        comentario.visivel = bool(row['visivel'])
        COMENTARIOS_POSTS_DB.append(comentario)
        post = POSTS_DB.get(comentario.post_id)
        if post:
            post.adicionar_comentario(comentario.id)

    cursor.execute('SELECT * FROM post_likes ORDER BY id ASC')
    for row in cursor.fetchall():
        post = POSTS_DB.get(row['post_id'])
        if post and row['email_usuario'] not in post.usuarios_curtidas:
            post.usuarios_curtidas.append(row['email_usuario'])

    cursor.execute('SELECT * FROM amizades ORDER BY id ASC')
    for row in cursor.fetchall():
        amizade = SolicitacaoAmizade(row['id'], row['email_solicitante'], row['email_receptor'])
        amizade.status = row['status']
        amizade.data_solicitacao = _dt_from_db(row['data_solicitacao']) or amizade.data_solicitacao
        amizade.data_aceito = _dt_from_db(row['data_aceito']) if 'data_aceito' in row.keys() else None
        chave = f"{min(amizade.email_solicitante, amizade.email_receptor)}_{max(amizade.email_solicitante, amizade.email_receptor)}"
        AMIZADES_DB[chave] = amizade

    cursor.execute('SELECT * FROM biblioteca ORDER BY id ASC')
    for row in cursor.fetchall():
        item = BibliotecaJogo(row['id'], row['email_usuario'], row['jogo_id'], row['platinado'] and 'steam' or 'manual')
        item.data_adicao = _dt_from_db(row['data_adicao']) or item.data_adicao
        item.tempo_jogado_horas = row['tempo_jogado_horas'] or 0
        item.concluido = bool(row['concluido'])
        item.platinado = bool(row['platinado'])
        BIBLIOTECA_DB[f"{item.email_usuario}_{item.jogo_id}"] = item

    cursor.execute('SELECT * FROM reviews ORDER BY id ASC')
    for row in cursor.fetchall():
        review = Review(row['id'], row['jogo_id'], row['email_usuario'], row['titulo'], row['conteudo'], row['nota'])
        review.data_criacao = _dt_from_db(row['data_criacao']) or review.data_criacao
        review.visivel = bool(row['visivel'])
        review.curtidas = row['curtidas'] or 0
        REVIEWS_DB[review.id] = review

    cursor.execute('SELECT * FROM review_comentarios ORDER BY id ASC')
    for row in cursor.fetchall():
        comentario = ComentarioReview(row['id'], row['review_id'], row['email_usuario'], row['texto'])
        comentario.data_criacao = _dt_from_db(row['data_criacao']) or comentario.data_criacao
        comentario.visivel = bool(row['visivel'])
        REVIEW_COMENTARIOS_DB.append(comentario)
        review = REVIEWS_DB.get(comentario.review_id)
        if review:
            review.adicionar_comentario(comentario.id)

    cursor.execute('SELECT * FROM notificacoes ORDER BY id ASC')
    for row in cursor.fetchall():
        notif = Notificacao(row['id'], row['email_receptor'], row['tipo'], row['titulo'], row['descricao'], row['link'])
        notif.data_criacao = _dt_from_db(row['data_criacao']) or notif.data_criacao
        notif.lida = bool(row['lida'])
        NOTIFICACOES_DB.setdefault(notif.email_receptor, []).append(notif)

    cursor.execute('SELECT * FROM mensagens ORDER BY id ASC')
    for row in cursor.fetchall():
        mensagem = Mensagem(row['id'], row['email_remetente'], row['email_destino'], row['conteudo'])
        mensagem.data_envio = _dt_from_db(row['data_envio']) or mensagem.data_envio
        MENSAGENS_DB.append(mensagem)

    conn.close()
    return {
        'categorias_db': categorias_db,
    }


def persistir_usuario(user):
    conn = get_connection()
    try:
        _ensure_usuario_columns(conn)
        cursor = conn.cursor()
        cursor.execute('PRAGMA table_info(usuarios)')
        colunas = {row[1] for row in cursor.fetchall()}

        campos_insert = ['nome', 'email', 'password']
        valores_insert = [user.nome, user.email, user._Usuario__password if hasattr(user, '_Usuario__password') else '']

        if 'token_recuperacao' in colunas:
            campos_insert.append('token_recuperacao')
            valores_insert.append(getattr(user, 'token_recuperacao', None))
        if 'idade' in colunas:
            campos_insert.append('idade')
            valores_insert.append(getattr(user, 'idade', None))
        if 'gosto_jogos' in colunas:
            campos_insert.append('gosto_jogos')
            valores_insert.append(getattr(user, 'gosto_jogos', ''))
        if 'telefone' in colunas:
            campos_insert.append('telefone')
            valores_insert.append(getattr(user, 'telefone', ''))
        if 'steam_id64' in colunas:
            campos_insert.append('steam_id64')
            valores_insert.append(getattr(user, 'steam_id64', ''))
        if 'steam_api_key' in colunas:
            campos_insert.append('steam_api_key')
            valores_insert.append(getattr(user, 'steam_api_key', ''))
        if 'hydra_account_email' in colunas:
            campos_insert.append('hydra_account_email')
            valores_insert.append(getattr(user, 'hydra_account_email', ''))
        if 'hydra_usuario' in colunas:
            campos_insert.append('hydra_usuario')
            valores_insert.append(getattr(user, 'hydra_usuario', ''))
        if 'hydra_pin' in colunas:
            campos_insert.append('hydra_pin')
            valores_insert.append(getattr(user, 'hydra_pin', ''))
        if 'hydra_token' in colunas:
            campos_insert.append('hydra_token')
            valores_insert.append(getattr(user, 'hydra_token', ''))
        if 'hydra_current_game' in colunas:
            campos_insert.append('hydra_current_game')
            valores_insert.append(getattr(user, 'hydra_current_game', ''))
        if 'hydra_last_update' in colunas:
            campos_insert.append('hydra_last_update')
            valores_insert.append(getattr(user, 'hydra_last_update', None))
        if 'foto_perfil' in colunas:
            campos_insert.append('foto_perfil')
            valores_insert.append(getattr(user, 'foto_perfil', ''))
        if 'data_cadastro' in colunas:
            campos_insert.append('data_cadastro')
            valores_insert.append(_dt_to_db(getattr(user, 'data_cadastro', None)))
        if 'is_admin' in colunas:
            campos_insert.append('is_admin')
            valores_insert.append(1 if user.__class__.__name__ == 'Admin' else 0)

        placeholders = ', '.join('?' for _ in campos_insert)
        upsert_columns = []
        for campo in campos_insert:
            if campo == 'email':
                continue
            upsert_columns.append(f'{campo}=excluded.{campo}')

        cursor.execute(
            f'''
            INSERT INTO usuarios ({', '.join(campos_insert)})
            VALUES ({placeholders})
            ON CONFLICT(email) DO UPDATE SET {', '.join(upsert_columns)}
            ''',
            valores_insert,
        )
        conn.commit()
    finally:
        conn.close()


def persistir_categoria(categoria):
    conn = get_connection()
    conn.execute(
        'INSERT INTO categorias (id, nome) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome',
        (categoria.id, categoria.nome),
    )
    conn.commit()
    conn.close()


def persistir_jogo(jogo, categorias=None):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO jogos (id, titulo, genero, desenvolvedora, ano) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET titulo=excluded.titulo, genero=excluded.genero,
            desenvolvedora=excluded.desenvolvedora, ano=excluded.ano
        ''',
        (jogo.id, jogo.titulo, jogo.genero, jogo.desenvolvedora, jogo.ano),
    )
    conn.execute('DELETE FROM jogo_categoria WHERE jogo_id = ?', (jogo.id,))
    categorias = categorias or []
    for categoria in categorias:
        categoria_id = getattr(categoria, 'id', categoria)
        conn.execute('INSERT OR IGNORE INTO jogo_categoria (jogo_id, categoria_id) VALUES (?, ?)', (jogo.id, categoria_id))
    conn.commit()
    conn.close()


def remover_jogo(jogo_id: int):
    conn = get_connection()
    conn.execute('DELETE FROM jogo_categoria WHERE jogo_id = ?', (jogo_id,))
    conn.execute('DELETE FROM jogos WHERE id = ?', (jogo_id,))
    conn.commit()
    conn.close()


def excluir_usuario_completo(email: str):
    email = (email or '').strip().lower()
    if not email:
        raise ValueError('Email do usuário é obrigatório')

    conn = get_connection()
    try:
        conn.execute('BEGIN')
        foto_relativa = None
        usuario_row = conn.execute('SELECT foto_perfil FROM usuarios WHERE lower(email) = ?', (email,)).fetchone()
        if usuario_row:
            foto_relativa = usuario_row['foto_perfil'] or ''

        conn.execute('DELETE FROM usuarios WHERE lower(email) = ?', (email,))
        conn.commit()

        if foto_relativa:
            if foto_relativa.startswith('/static/uploads/'):
                nome_arquivo = foto_relativa.split('/static/uploads/', 1)[1]
                caminho_arquivo = os.path.join(BASE_DIR, 'static', 'uploads', nome_arquivo)
                if os.path.exists(caminho_arquivo):
                    os.remove(caminho_arquivo)
            elif foto_relativa.startswith('static/uploads/'):
                caminho_arquivo = os.path.join(BASE_DIR, foto_relativa)
                if os.path.exists(caminho_arquivo):
                    os.remove(caminho_arquivo)
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def persistir_post(post):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO posts (id, autor_email, titulo, conteudo, imagem_url, data_criacao, visivel)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET autor_email=excluded.autor_email, titulo=excluded.titulo,
            conteudo=excluded.conteudo, imagem_url=excluded.imagem_url, data_criacao=excluded.data_criacao,
            visivel=excluded.visivel
        ''',
        (post.id, post.autor_email, post.titulo, post.conteudo, post.imagem_url, _dt_to_db(post.data_criacao), 1 if post.visivel else 0),
    )
    conn.commit()
    conn.close()


def persistir_comentario_post(comentario):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO comentarios (id, post_id, autor_email, texto, data_criacao, visivel)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET post_id=excluded.post_id, autor_email=excluded.autor_email,
            texto=excluded.texto, data_criacao=excluded.data_criacao, visivel=excluded.visivel
        ''',
        (comentario.id, comentario.post_id, comentario.autor_email, comentario.texto, _dt_to_db(comentario.data_criacao), 1 if comentario.visivel else 0),
    )
    conn.commit()
    conn.close()


def marcar_post_visivel(post_id: int, visivel: bool):
    conn = get_connection()
    conn.execute('UPDATE posts SET visivel = ? WHERE id = ?', (1 if visivel else 0, post_id))
    conn.commit()
    conn.close()


def marcar_comentario_post_visivel(comentario_id: int, visivel: bool):
    conn = get_connection()
    conn.execute('UPDATE comentarios SET visivel = ? WHERE id = ?', (1 if visivel else 0, comentario_id))
    conn.commit()
    conn.close()


def persistir_post_like(post_id: int, email_usuario: str, curtido: bool):
    conn = get_connection()
    if curtido:
        conn.execute('INSERT OR IGNORE INTO post_likes (post_id, email_usuario) VALUES (?, ?)', (post_id, email_usuario))
    else:
        conn.execute('DELETE FROM post_likes WHERE post_id = ? AND email_usuario = ?', (post_id, email_usuario))
    conn.commit()
    conn.close()


def persistir_amizade(amizade):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO amizades (id, email_solicitante, email_receptor, status, data_solicitacao, data_aceito)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email_solicitante, email_receptor) DO UPDATE SET
            status=excluded.status,
            data_solicitacao=excluded.data_solicitacao,
            data_aceito=excluded.data_aceito
        ''',
        (
            amizade.id,
            amizade.email_solicitante,
            amizade.email_receptor,
            amizade.status,
            _dt_to_db(amizade.data_solicitacao),
            _dt_to_db(getattr(amizade, 'data_aceito', None)),
        ),
    )
    conn.commit()
    conn.close()


def remover_amizade(email1: str, email2: str):
    conn = get_connection()
    conn.execute(
        'DELETE FROM amizades WHERE (email_solicitante = ? AND email_receptor = ?) OR (email_solicitante = ? AND email_receptor = ?)',
        (email1, email2, email2, email1),
    )
    conn.commit()
    conn.close()


def persistir_biblioteca_item(item):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO biblioteca (id, email_usuario, jogo_id, data_adicao, tempo_jogado_horas, concluido, platinado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email_usuario, jogo_id) DO UPDATE SET
            data_adicao=excluded.data_adicao,
            tempo_jogado_horas=excluded.tempo_jogado_horas,
            concluido=excluded.concluido,
            platinado=excluded.platinado
        ''',
        (item.id, item.email_usuario, item.jogo_id, _dt_to_db(item.data_adicao), item.tempo_jogado_horas, 1 if item.concluido else 0, 1 if item.platinado else 0),
    )
    conn.commit()
    conn.close()


def remover_biblioteca_item(email_usuario: str, jogo_id: int):
    conn = get_connection()
    conn.execute('DELETE FROM biblioteca WHERE email_usuario = ? AND jogo_id = ?', (email_usuario, jogo_id))
    conn.commit()
    conn.close()


def persistir_review(review):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO reviews (id, jogo_id, email_usuario, titulo, conteudo, nota, data_criacao, visivel, curtidas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            jogo_id=excluded.jogo_id,
            email_usuario=excluded.email_usuario,
            titulo=excluded.titulo,
            conteudo=excluded.conteudo,
            nota=excluded.nota,
            data_criacao=excluded.data_criacao,
            visivel=excluded.visivel,
            curtidas=excluded.curtidas
        ''',
        (review.id, review.jogo_id, review.email_usuario, review.titulo, review.conteudo, review.nota, _dt_to_db(review.data_criacao), 1 if review.visivel else 0, review.curtidas),
    )
    conn.commit()
    conn.close()


def persistir_review_comentario(comentario):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO review_comentarios (id, review_id, email_usuario, texto, data_criacao, visivel)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET review_id=excluded.review_id, email_usuario=excluded.email_usuario,
            texto=excluded.texto, data_criacao=excluded.data_criacao, visivel=excluded.visivel
        ''',
        (comentario.id, comentario.review_id, comentario.email_usuario, comentario.texto, _dt_to_db(comentario.data_criacao), 1 if comentario.visivel else 0),
    )
    conn.commit()
    conn.close()


def marcar_review_visivel(review_id: int, visivel: bool):
    conn = get_connection()
    conn.execute('UPDATE reviews SET visivel = ? WHERE id = ?', (1 if visivel else 0, review_id))
    conn.commit()
    conn.close()


def marcar_review_comentario_visivel(comentario_id: int, visivel: bool):
    conn = get_connection()
    conn.execute('UPDATE review_comentarios SET visivel = ? WHERE id = ?', (1 if visivel else 0, comentario_id))
    conn.commit()
    conn.close()


def persistir_notificacao(notif):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO notificacoes (id, email_receptor, tipo, titulo, descricao, link, data_criacao, lida)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email_receptor=excluded.email_receptor,
            tipo=excluded.tipo,
            titulo=excluded.titulo,
            descricao=excluded.descricao,
            link=excluded.link,
            data_criacao=excluded.data_criacao,
            lida=excluded.lida
        ''',
        (notif.id, notif.email_receptor, notif.tipo, notif.titulo, notif.descricao, notif.link, _dt_to_db(notif.data_criacao), 1 if notif.lida else 0),
    )
    conn.commit()
    conn.close()


def marcar_notificacao_lida(email_receptor: str, notif_id: int):
    conn = get_connection()
    conn.execute('UPDATE notificacoes SET lida = 1 WHERE email_receptor = ? AND id = ?', (email_receptor, notif_id))
    conn.commit()
    conn.close()


def persistir_mensagem(mensagem):
    conn = get_connection()
    conn.execute(
        '''
        INSERT INTO mensagens (id, email_remetente, email_destino, conteudo, data_envio)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email_remetente=excluded.email_remetente,
            email_destino=excluded.email_destino,
            conteudo=excluded.conteudo,
            data_envio=excluded.data_envio
        ''',
        (mensagem.id, mensagem.email_remetente, mensagem.email_destino, mensagem.conteudo, _dt_to_db(mensagem.data_envio)),
    )
    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    seed_initial_data()
    print(f'Banco de dados criado em: {DB_PATH}')
