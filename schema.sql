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
