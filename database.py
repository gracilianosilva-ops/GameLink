import os
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
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def init_db():
    if not os.path.exists(DB_PATH):
        conn = get_connection()
        conn.executescript(SCHEMA)
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


if __name__ == '__main__':
    init_db()
    seed_initial_data()
    print(f'Banco de dados criado em: {DB_PATH}')
