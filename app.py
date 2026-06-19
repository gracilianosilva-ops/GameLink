from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from modelos.usuario import Usuario, Admin, USUARIOS_DB
from modelos.jogo import Jogo, Categoria, JOGOS_DB
from modelos.posts import Post, Comentario, POSTS_DB, COMENTARIOS_POSTS_DB
from modelos.amigos_biblioteca import (
    GerenciadorAmigos, GerenciadorBiblioteca, GerenciadorReviews, 
    GerenciadorNotificacoes, AMIZADES_DB, BIBLIOTECA_DB, REVIEWS_DB, NOTIFICACOES_DB
)
import json
import os
from functools import lru_cache
from urllib.parse import quote
from urllib.request import urlopen
from werkzeug.utils import secure_filename
from datetime import datetime
from excecao import GameLinkException, AutenticacaoError, OperacaoInvalidaError
from database import init_db

app = Flask(__name__)
app.secret_key = "super_secret_key_gamelink"

# Inicializa o banco de dados SQLite se ainda não existir
init_db()

# Configuração de uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _capa_fallback(titulo: str) -> str:
    texto = quote((titulo or 'Jogo')[:30])
    return f'https://placehold.co/600x900/0b1220/38bdf8?text={texto}'


@lru_cache(maxsize=256)
def obter_capa_jogo(titulo: str) -> str:
    if not titulo:
        return _capa_fallback('Jogo')

    consultas = [
        titulo,
        f'{titulo} video game',
        f'{titulo} game',
    ]

    for consulta in consultas:
        try:
            url_api = (
                'https://en.wikipedia.org/w/api.php?'
                'action=query&format=json&origin=*&redirects=1'
                '&generator=search&gsrnamespace=0&gsrlimit=1'
                '&prop=pageimages&piprop=thumbnail&pithumbsize=600'
                f'&gsrsearch={quote(consulta)}'
            )
            with urlopen(url_api, timeout=2) as resposta:
                dados = json.loads(resposta.read().decode('utf-8'))

            paginas = dados.get('query', {}).get('pages', {})
            for pagina in paginas.values():
                thumb = pagina.get('thumbnail', {}).get('source')
                if thumb:
                    return thumb
        except Exception:
            continue

    return _capa_fallback(titulo)


def montar_biblioteca_cards(email: str) -> list:
    cards = []
    for item in GerenciadorBiblioteca.obter_biblioteca(email):
        jogo = JOGOS_DB.get(item.jogo_id)
        if not jogo:
            continue
        cards.append({
            'item': item,
            'jogo': jogo,
            'capa_url': obter_capa_jogo(jogo.titulo),
            'esta_na_biblioteca': True,
        })
    return cards


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
        'sugeridos': sugeridos[:6],
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
CATEGORIAS_DB = {}
if not JOGOS_DB:
    c1 = Categoria(1, "RPG")
    c2 = Categoria(2, "Ação")
    CATEGORIAS_DB[1] = c1
    CATEGORIAS_DB[2] = c2
    
    j1 = Jogo(1, "The Witcher 3", "RPG", "CD Projekt Red", 2015)
    j1.associar_categoria(c1)
    j2 = Jogo(2, "Elden Ring", "RPG", "FromSoftware", 2022)
    j2.associar_categoria(c1)
    j3 = Jogo(3, "GTA V", "Ação", "Rockstar", 2013)
    j3.associar_categoria(c2)
    
    JOGOS_DB[1] = j1
    JOGOS_DB[2] = j2
    JOGOS_DB[3] = j3
    USUARIOS_DB["admin@gamelink.com"] = Admin(1, "Caxa", "admin@gamelink.com", "admin123", nivel_acesso=5)

# --- Rotas de Autenticação ---
@app.route('/')
def index(): 
    return redirect(url_for('login'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        if email in USUARIOS_DB:
            flash("E-mail já cadastrado!", "danger")
        else:
            USUARIOS_DB[email] = Usuario(len(USUARIOS_DB) + 1, nome, email, senha)
            flash("Cadastro realizado!", "success")
            return redirect(url_for('login'))
    return render_template('cadastro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        user = USUARIOS_DB.get(email)
        if user and user.verificar_senha(senha):
            session['user_email'] = user.email
            session['user_nome'] = user.nome
            session['is_admin'] = isinstance(user, Admin)
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
    jogos = list(JOGOS_DB.values())
    for jogo in jogos:
        jogo.capa_url = obter_capa_jogo(jogo.titulo)

    posts_visiveis = {k: v for k, v in POSTS_DB.items() if v.visivel}
    comentarios_visiveis = [c for c in COMENTARIOS_POSTS_DB if c.visivel]
    notif_list = GerenciadorNotificacoes.obter_notificacoes(meu_email)
    notif_nao_lidas = GerenciadorNotificacoes.contar_nao_lidas(meu_email)
    biblioteca_cards = montar_biblioteca_cards(meu_email)
    contexto_amigos = montar_amigos_contexto(meu_email)
    
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
        amigos_emails=contexto_amigos['amigos_emails'],
        solicitacoes_pendentes=contexto_amigos['pendentes'],
        usuarios_sugeridos=contexto_amigos['sugeridos']
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
        jogo.associar_categoria(categoria_existente)
        
        JOGOS_DB[novo_id] = jogo
        flash("Jogo cadastrado!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('dashboard'))

@app.route('/jogos/deletar/<int:id>')
def deletar_jogo(id):
    if session.get('is_admin') and id in JOGOS_DB: 
        del JOGOS_DB[id]
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

    for jogo in JOGOS_DB.values():
        if filtro == 'titulo' and termo in jogo.titulo.lower():
            resultados.append(jogo)
        elif filtro == 'genero' and termo in jogo.genero.lower():
            resultados.append(jogo)

    for jogo in resultados:
        jogo.capa_url = obter_capa_jogo(jogo.titulo)

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
    amigos = GerenciadorAmigos.obter_amigos(email)
    
    # === SISTEMA DE RELACIONAMENTO DEDICADO ===
    sao_amigos = False
    tem_solicitacao_pendente = False
    
    if meu_email and meu_email != email:
        sao_amigos = GerenciadorAmigos.sao_amigos(meu_email, email)
        
        solicitacoes_para_mim = GerenciadorAmigos.obter_solicitacoes_pendentes(meu_email)
        for sol in solicitacoes_para_mim:
            if sol.email_solicitante == email:
                tem_solicitacao_pendente = True
                break

    return render_template(
        'perfil.html', 
        usuario=user, 
        amigos=amigos, 
        usuarios=USUARIOS_DB, 
        jogos=list(JOGOS_DB.values()),
        comentarios=[c for c in COMENTARIOS_POSTS_DB if c.visivel],
        sao_amigos=sao_amigos,
        tem_solicitacao_pendente=tem_solicitacao_pendente
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
    
    user.nome = request.form.get('nome', user.nome)
    idade_str = request.form.get('idade', '').strip()
    user.idade = int(idade_str) if idade_str else None
    user.gosto_jogos = request.form.get('gosto_jogos', '')
    user.telefone = request.form.get('telefone', '')
    
    session['user_nome'] = user.nome
    flash("Perfil atualizado com sucesso!", "success")
    return redirect(url_for('perfil', email=session['user_email']))

@app.route('/amizade/adicionar/<email_alvo>')
def adicionar_amigo(email_alvo):
    meu_email = session.get('user_email')
    if not meu_email or meu_email == email_alvo:
        return redirect(url_for('dashboard'))
    try:
        # 1. Envia a solicitação de amizade
        id_solicitacao = max([s.id for s in AMIZADES_DB.values()], default=0) + 1
        GerenciadorAmigos.enviar_solicitacao(id_solicitacao, meu_email, email_alvo)
        
        # Criamos um ID incremental para a notificação buscar de todas as listas de usuários
        todas_notifs = [n for lista in NOTIFICACOES_DB.values() for n in lista]
        id_notif = max([n.id for n in todas_notifs], default=0) + 1
        
        GerenciadorNotificacoes.criar_notificacao(
            id_notif=id_notif,
            email_receptor=email_alvo,       # Quem recebe é o alvo
            tipo='amizade',                  # Tipo esperado pelo seu html
            titulo='👥 Nova Solicitação de Amizade!',
            descricao=f'{meu_email} enviou um pedido de amizade para você.',
            link=f'/perfil/{meu_email}' # Link para visitar o perfil e aceitar
        )

        flash("Solicitação de amizade enviada!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_alvo))

@app.route('/amizade/aceitar/<email_amigo>')
def aceitar_amizade(email_amigo):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.aceitar_solicitacao(meu_email, email_amigo)
        
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

        flash("Amizade aceita!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_amigo)) # Redireciona de volta para o perfil do seu novo amigo

@app.route('/amizade/recusar/<email_amigo>')
def recusar_amizade(email_amigo):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.recusar_solicitacao(meu_email, email_amigo)
        flash("Solicitação recusada!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for('perfil', email=email_amigo)) #Mantém no perfil

@app.route('/amizade/remover/<email_amigo>')
def remover_amigo(email_amigo):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorAmigos.recusar_solicitacao(meu_email, email_amigo)
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
        GerenciadorBiblioteca.adicionar_jogo(id_biblioteca, meu_email, jogo_id)
        flash("Jogo adicionado à biblioteca!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/biblioteca/remover/<int:jogo_id>')
def remover_biblioteca(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    try:
        GerenciadorBiblioteca.remover_jogo(meu_email, jogo_id)
        flash("Jogo removido da biblioteca!", "info")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/biblioteca')
def minha_biblioteca():
    meu_email = session.get('user_email')
    if not meu_email: 
        return redirect(url_for('login'))
    biblioteca_cards = montar_biblioteca_cards(meu_email)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
        return render_template('_biblioteca_conteudo.html', biblioteca_cards=biblioteca_cards, jogos=JOGOS_DB, usuarios=USUARIOS_DB)
    return render_template('biblioteca.html', biblioteca_cards=biblioteca_cards, jogos=JOGOS_DB, usuarios=USUARIOS_DB)

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
    nota = request.form.get('nota', 5)
    
    try:
        nota = int(nota)
        res = moderate_text(titulo)
        res_c = moderate_text(conteudo)
        if not res.get('allowed', True) or not res_c.get('allowed', True):
            flash("Seu review contém conteúdo impróprio!", "danger")
            return redirect(url_for('perfil', email=meu_email))
        
        if not titulo or not conteudo:
            flash("Título e conteúdo são obrigatórios!", "danger")
            return redirect(url_for('perfil', email=meu_email))
        
        id_review = max(REVIEWS_DB.keys(), default=0) + 1
        GerenciadorReviews.criar_review(id_review, jogo_id, meu_email, titulo, conteudo, nota)
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
    return jsonify({'curtidas': review.curtidas})

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
        return jsonify({'sucesso': True})
    except Exception as e:
        return jsonify({'erro': str(e)}), 400

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
    POSTS_DB[novo_id] = Post(novo_id, session['user_email'], titulo, conteudo, imagem_url)
    
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
    session.clear()
    return redirect(url_for('login'))

# --- Rotas de API para AJAX ---
@app.route('/api/reviews/usuario/<email>')
def api_reviews_usuario(email):
    reviews = GerenciadorReviews.obter_reviews_usuario(email)
    reviews_data = []
    for review in reviews:
        jogo = JOGOS_DB.get(review.jogo_id)
        reviews_data.append({
            'id': review.id,
            'titulo': review.titulo,
            'conteudo': review.conteudo,
            'nota': review.nota,
            'jogo_titulo': jogo.titulo if jogo else f"Jogo #{review.jogo_id}",
            'data': review.data_criacao.strftime('%d/%m/%Y')
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

if __name__ == '__main__':
    app.run(debug=True)