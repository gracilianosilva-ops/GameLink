# GameLink - Documentação Detalhada

## Visão geral do projeto

GameLink é uma aplicação web em Flask que simula uma rede social para jogadores. O código combina:
- autenticação de usuários
- cadastro e login
- biblioteca de jogos pessoal
- integração com Steam e Hydra
- sistema de amigos, mensagens e notificações
- posts, comentários e reviews
- persistência em banco de dados SQLite

## Estrutura principal

### `app.py`
É o arquivo principal da aplicação. Ele contém:
- configuração do Flask
- carregamento de `.env`
- inicialização do banco de dados com `init_db()`
- definição de rotas HTTP e lógicas de negócio
- helpers para Steam, Hydra e geração de capas de jogos
- inicialização do servidor e fallback para navegador/webview

#### Fluxos principais

- `/_carregar_env_local()`
  - lê arquivo `.env` local e define variáveis de ambiente se não existirem.

- `init_db()` e `carregar_estado_persistido()`
  - garantem que `gamelink.db` existe e carregam dados pendentes para memória.

- `cadastro()`
  - faz cadastro com verificação de código via SMTP ou exibe o código localmente
  - salva o usuário em `USUARIOS_DB` e em SQLite com `persistir_usuario()`

- `login()`
  - valida credenciais contra objetos em `USUARIOS_DB`
  - cria sessão Flask com `user_email`, `user_nome`, `is_admin`

- `dashboard()`
  - exibe jogos, posts, biblioteca, notificações e amigos
  - sincroniza Steam/Hydra quando necessário

- `perfil()`
  - mostra perfil de usuário, biblioteca, reviews, Steam e Hydra
  - apóia envio de solicitações, importação de Steam/Hydra e edição de perfil

- `salvar_perfil()`
  - atualiza dados do usuário e salva em SQLite
  - aceita upload de imagem de perfil

- Hydra/Steam
  - `montar_steam_contexto()`, `sincronizar_status_steam()`
  - `montar_hydra_contexto()`, `importar_hydra_exportacao()`, `hydra_detectar_sessao_local()`

- Rotas de rede social
  - criar posts, comentar, curtir, enviar mensagens, aceitar amizade, etc.

### `database.py`
Responsável por todos os dados persistidos no SQLite.

#### O que contém
- esquema SQL em `SCHEMA`
- `get_connection()` para conexão SQLite com `PRAGMA foreign_keys = ON`
- `init_db()` para criar tabelas e atualizar colunas
- funções de persistência específicas, por exemplo:
  - `persistir_usuario()`
  - `persistir_jogo()`
  - `persistir_post()`
  - `persistir_comentario_post()`
  - `persistir_biblioteca_item()`
  - `persistir_review()`
  - `persistir_notificacao()`
  - `persistir_mensagem()`
- `reset_db()` para recriar o banco e semear dados iniciais

#### Dados carregados em memória
- `USUARIOS_DB`
- `JOGOS_DB`
- `POSTS_DB`
- `COMENTARIOS_POSTS_DB`
- `AMIZADES_DB`
- `BIBLIOTECA_DB`
- `REVIEWS_DB`
- `REVIEW_COMENTARIOS_DB`
- `NOTIFICACOES_DB`
- `MENSAGENS_DB`

### `modelos/usuario.py`
Define as classes de usuário.
- `Usuario`
- `Admin` (herda de `Usuario`)
- `USUARIOS_DB` em memória

Funcionalidades principais:
- validação de senha
- status Steam/Hydra/Discord
- geração de links de Discord
- métodos de recuperação de senha e estado geral

### `modelos/jogo.py`
Define:
- `Categoria`
- `Jogo`
- `JOGOS_DB` em memória

Funcionalidades:
- associação de categoria a jogo
- listagem de categorias

### `modelos/posts.py`
Define:
- `Post`
- `Comentario`
- `POSTS_DB`
- `COMENTARIOS_POSTS_DB`

Funcionalidades:
- criar posts e comentários
- curtir posts
- controlar visibilidade

### `modelos/amigos_biblioteca.py`
Define várias estruturas de domínio e gerenciadores:
- `SolicitacaoAmizade`
- `BibliotecaJogo`
- `Review`
- `ComentarioReview`
- `Notificacao`
- `Mensagem`
- `GerenciadorMensagens`
- `GerenciadorAmigos`
- `GerenciadorBiblioteca`
- `GerenciadorReviews`

Essa camada implementa regras de negócio em memória e dá suporte a todos os recursos sociais.

### `modelos/moderação de conteudo.py`
É carregado dinamicamente por `app.py`.
- se falhar, existe um fallback simples em `app.py`
- usado para validar texto de posts e comentários

## Limpeza aplicada

### Remoções e ajustes
- removidos imports redundantes de `app.py`:
  - `sqlite3`
  - `GameLinkException`
  - `OperacaoInvalidaError`
  - `webview` no topo do arquivo
- mantido apenas o import local de `webview` no bloco final, onde ele é realmente usado
- verificado que `app.py` compila com `python -m py_compile app.py`
- removidos diretórios `__pycache__/` e `modelos/__pycache__/`

### Observações
- existem arquivos em `modelos/` que não são importados no aplicativo principal:
  - `modelos/perfil.py`
  - `modelos/interações.py`
  Esses arquivos parecem ser módulos auxiliares ou testes não utilizados.

## Como rodar o sistema

1. instalar dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. executar o app:
   ```bash
   python app.py
   ```
3. abrir no navegador:
   ```
   http://127.0.0.1:5000
   ```

### Observação de e-mail
- se não definir `MAIL_HOST`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, o cadastro fica em modo de teste e mostra o código na tela.

## Recomendações para próximo passo

- adicionar um `.gitignore` para ignorar `__pycache__/`, `*.pyc`, `.venv/`, `gamelink.db`, `.env`
- remover ou mover `modelos/perfil.py` e `modelos/interações.py` se não forem usados
- dividir `app.py` em módulos menores se quiser reduzir acoplamento e melhorar manutenção

---

## Mapa rápido de arquivos

- `app.py`: aplicativo Flask + lógica
- `database.py`: SQLite + persistência
- `modelos/usuario.py`: modelos de usuário
- `modelos/jogo.py`: modelos de jogo e categoria
- `modelos/posts.py`: modelos de publicação
- `modelos/amigos_biblioteca.py`: amigos, biblioteca, reviews, notificações, mensagens
- `templates/`: páginas HTML
- `static/uploads/`: uploads de imagem de perfil
