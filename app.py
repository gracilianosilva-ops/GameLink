from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from modelos.usuario import Usuario, Admin, USUARIOS_DB
from modelos.jogo import Jogo, Categoria, JOGOS_DB
from modelos.posts import Post, Comentario, POSTS_DB, COMENTARIOS_POSTS_DB
from modelos.amigos_biblioteca import (
    GerenciadorAmigos, GerenciadorBiblioteca, GerenciadorReviews, 
    GerenciadorNotificacoes, AMIZADES_DB, BIBLIOTECA_DB, REVIEWS_DB, NOTIFICACOES_DB
)
import sys
import importlib.util
import os
from werkzeug.utils import secure_filename
from datetime import datetime

# Importar módulo com espaço no nome
spec = importlib.util.spec_from_file_location("moderacao", "modelos/moderação de conteudo.py")
moderacao = importlib.util.module_from_spec(spec)
spec.loader.exec_module(moderacao)
moderate_text = moderacao.moderate_text
is_allowed = moderacao.is_allowed
DEFAULT_BLOCKED_TERMS = moderacao.DEFAULT_BLOCKED_TERMS

from excecao import GameLinkException, AutenticacaoError

app = Flask(__name__)
app.secret_key = "super_secret_key_gamelink"

# Configuração de uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Estruturas de Dados para Funcionalidades ---
COMENTARIOS = [] # Lista: {'id', 'jogo_id', 'email', 'texto', 'visivel'}
AMIZADES = []    # Lista: (email_solicitante, email_receptor, status)
PALAVRAS_PROIBIDAS = ['spam', 'ofensa', 'impróprio']

# Carga inicial de dados
if not JOGOS_DB:
    c1 = Categoria(1, "RPG")
    c2 = Categoria(2, "Ação")
    j1 = Jogo(1, "The Witcher 3", "RPG", "CD Projekt Red", 2015)
    j1.associar_categoria(c1)
    j2 = Jogo(2, "Elden Ring", "RPG", "FromSoftware", 2022)
    j2.associar_categoria(c1)
    j3 = Jogo(3, "GTA V", "Ação", "Rockstar", 2013)
    j3.associar_categoria(c2)
    JOGOS_DB[1] = j1
    JOGOS_DB[2] = j2
    JOGOS_DB[3] = j3
    USUARIOS_DB["admin@gamelink.com"] = Admin(1, "Boss", "admin@gamelink.com", "admin123", nivel_acesso=5)

# --- Rotas de Autenticação ---
@app.route('/')
def index(): return redirect(url_for('login'))

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
            # Em um sistema real, aqui enviaria um e-mail.
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
        except Exception:
            flash("Token inválido.", "danger")
    return redirect(url_for('recuperar'))

# --- Rotas de Dashboard e Jogos ---
@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session: return redirect(url_for('login'))
    # Filtra apenas posts visíveis
    posts_visiveis = {k: v for k, v in POSTS_DB.items() if v.visivel}
    comentarios_visiveis = [c for c in COMENTARIOS_POSTS_DB if c.visivel]
    
    # Obter notificações não lidas
    notif_nao_lidas = GerenciadorNotificacoes.contar_nao_lidas(session['user_email'])
    
    return render_template('dashboard.html', jogos=JOGOS_DB, usuarios=USUARIOS_DB, comentarios=COMENTARIOS, posts=posts_visiveis, comentarios_posts=comentarios_visiveis, notif_nao_lidas=notif_nao_lidas)

@app.route('/jogos/novo', methods=['POST'])
def novo_jogo():
    if not session.get('is_admin'): return redirect(url_for('dashboard'))
    novo_id = max(JOGOS_DB.keys(), default=0) + 1
    JOGOS_DB[novo_id] = Jogo(novo_id, request.form['titulo'], request.form['genero'], request.form['desenvolvedora'], int(request.form['ano']))
    return redirect(url_for('dashboard'))

@app.route('/jogos/deletar/<int:id>')
def deletar_jogo(id):
    if session.get('is_admin') and id in JOGOS_DB: del JOGOS_DB[id]
    return redirect(url_for('dashboard'))

# --- Funcionalidades de Rede Social ---
@app.route('/perfil/<email>')
def perfil(email):
    if 'user_email' not in session: 
        return redirect(url_for('login'))
    user = USUARIOS_DB.get(email)
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    amigos = [a[1] if a[0] == email else a[0] for a in AMIZADES if email in a and a[2] == 'aceito']
    return render_template('perfil.html', usuario=user, amigos=amigos, usuarios=USUARIOS_DB, comentarios=COMENTARIOS, jogos=JOGOS_DB)

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
    
    # Atualiza os dados do perfil
    user.nome = request.form.get('nome', user.nome)
    idade_str = request.form.get('idade', '').strip()
    user.idade = int(idade_str) if idade_str else None
    user.gosto_jogos = request.form.get('gosto_jogos', '')
    user.telefone = request.form.get('telefone', '')
    
    # Atualiza o nome na sessão também
    session['user_nome'] = user.nome
    
    flash("Perfil atualizado com sucesso!", "success")
    return redirect(url_for('perfil', email=session['user_email']))

@app.route('/amizade/adicionar/<email_alvo>')
def adicionar_amigo(email_alvo):
    meu_email = session.get('user_email')
    if not meu_email or meu_email == email_alvo:
        return redirect(url_for('dashboard'))
    
    try:
        id_solicitacao = max([s.id for s in AMIZADES_DB.values()], default=0) + 1
        GerenciadorAmigos.enviar_solicitacao(id_solicitacao, meu_email, email_alvo)
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
        flash("Amizade aceita!", "success")
    except Exception as e:
        flash(str(e), "danger")
    
    return redirect(url_for('dashboard'))

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
    
    return redirect(url_for('dashboard'))

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
    
    return redirect(url_for('perfil', email=meu_email))

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
    
    biblioteca = GerenciadorBiblioteca.obter_biblioteca(meu_email)
    return render_template('biblioteca.html', biblioteca=biblioteca, jogos=JOGOS_DB, usuarios=USUARIOS_DB)

# --- Rotas de Reviews ---
@app.route('/jogo/<int:jogo_id>/review/novo', methods=['POST'])
def novo_review(jogo_id):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))
    
    if jogo_id not in JOGOS_DB:
        flash("Jogo não encontrado!", "danger")
        return redirect(url_for('dashboard'))
    
    # Verifica se jogo está na biblioteca
    if not GerenciadorBiblioteca.jogo_na_biblioteca(meu_email, jogo_id):
        flash("Você precisa adicionar o jogo à sua biblioteca para fazer review!", "danger")
        return redirect(url_for('dashboard'))
    
    titulo = request.form.get('titulo', '').strip()
    conteudo = request.form.get('conteudo', '').strip()
    nota = request.form.get('nota', 5)
    
    try:
        nota = int(nota)
        # Valida conteúdo
        if not moderate_text(titulo) or not moderate_text(conteudo):
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
    return render_template('notificacoes.html', notificacoes=notif_list, usuarios=USUARIOS_DB)

@app.route('/notificacao/<int:notif_id>/marcar-lida', methods=['POST'])
def marcar_notif_lida(notif_id):
    meu_email = session.get('user_email')
    if not meu_email:
        return redirect(url_for('login'))
    
    try:
        GerenciadorNotificacoes.marcar_como_lida(meu_email, notif_id)
        return jsonify({'sucesso': True})
    except Exception as e:
        return jsonify({'erro': str(e)}), 400

@app.route('/jogo/<int:jogo_id>/comentar', methods=['POST'])
def comentar(jogo_id):
    texto = request.form.get('texto', '').strip()
    if any(p in texto.lower() for p in PALAVRAS_PROIBIDAS):
        flash("Comentário impróprio!", "danger")
    elif texto:
        COMENTARIOS.append({'id': len(COMENTARIOS) + 1, 'jogo_id': jogo_id, 'email': session['user_email'], 'texto': texto, 'visivel': True})
    return redirect(url_for('dashboard'))

@app.route('/moderacao/excluir_comentario/<int:id>')
def excluir_comentario(id):
    if session.get('is_admin'):
        for c in COMENTARIOS:
            if c['id'] == id: c['visivel'] = False
    return redirect(url_for('dashboard'))

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
    
    # Verificar moderação de conteúdo
    resultado_titulo = moderate_text(titulo)
    resultado_conteudo = moderate_text(conteudo)
    
    if not resultado_titulo['allowed'] or not resultado_conteudo['allowed']:
        termos_bloqueados = resultado_titulo['blocked_terms'] + resultado_conteudo['blocked_terms']
        flash(f"Conteúdo contém termos impróprios: {', '.join(set(termos_bloqueados))}", "danger")
        return redirect(url_for('dashboard'))
    
    # Processar upload de imagem
    imagem_url = None
    if 'imagem' in request.files:
        file = request.files['imagem']
        if file and file.filename != '' and allowed_file(file.filename):
            # Gerar nome seguro para o arquivo
            filename = secure_filename(f"{session['user_email']}_{int(datetime.now().timestamp())}_{file.filename}")
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            imagem_url = f"/static/uploads/{filename}"
        elif file and file.filename != '' and not allowed_file(file.filename):
            flash("Tipo de arquivo não permitido. Use PNG, JPG, JPEG, GIF ou WEBP.", "danger")
            return redirect(url_for('dashboard'))
    
    # Criar novo post com imagem (se houver)
    novo_id = max(POSTS_DB.keys(), default=0) + 1
    post_criado = Post(novo_id, session['user_email'], titulo, conteudo, imagem_url)
    POSTS_DB[novo_id] = post_criado
    
    # Notificar amigos sobre o novo post
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
    
    # Obter comentários do post
    comentarios = [c for c in COMENTARIOS_POSTS_DB if c.post_id == post_id and c.visivel]
    autor = USUARIOS_DB.get(post.autor_email)
    
    return render_template('ver_post.html', post=post, comentarios=comentarios, autor=autor, usuarios=USUARIOS_DB)

@app.route('/posts/<int:post_id>/curtir', methods=['POST'])
def curtir_post(post_id):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    post = POSTS_DB.get(post_id)
    if not post:
        return jsonify({'error': 'Post não encontrado'}), 404
    
    email = session['user_email']
    if post.usuario_curtiu(email):
        post.descurtir(email)
        curtiu = False
    else:
        post.curtir(email)
        curtiu = True
    
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
    
    # Verificar moderação de conteúdo
    resultado = moderate_text(texto)
    if not resultado['allowed']:
        flash(f"Comentário contém termos impróprios: {', '.join(resultado['blocked_terms'])}", "danger")
        return redirect(url_for('ver_post', post_id=post_id))
    
    # Criar comentário
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
    
    # Apenas o autor ou admin pode deletar
    if session['user_email'] != post.autor_email and not session.get('is_admin'):
        flash("Você não tem permissão para deletar este post.", "danger")
        return redirect(url_for('ver_post', post_id=post_id))
    
    post.visivel = False
    flash("Post deletado com sucesso!", "success")
    return redirect(url_for('dashboard'))

@app.route('/comentario/<int:comentario_id>/deletar', methods=['POST'])
def deletar_comentario_post(comentario_id):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    comentario = next((c for c in COMENTARIOS_POSTS_DB if c.id == comentario_id), None)
    if not comentario:
        flash("Comentário não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    
    # Apenas o autor do comentário ou admin pode deletar
    if session['user_email'] != comentario.autor_email and not session.get('is_admin'):
        flash("Você não tem permissão para deletar este comentário.", "danger")
        return redirect(url_for('ver_post', post_id=comentario.post_id))
    
    comentario.visivel = False
    flash("Comentário deletado com sucesso!", "success")
    return redirect(url_for('ver_post', post_id=comentario.post_id))

@app.route('/moderacao/posts')
def painel_moderacao_posts():
    if not session.get('is_admin'):
        flash("Acesso restrito a administradores.", "danger")
        return redirect(url_for('dashboard'))
    
    # Posts ocultos para revisão
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
        flash("Post restaurado com sucesso!", "success")
    
    return redirect(url_for('painel_moderacao_posts'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/busca')
def busca():
    termo = request.args.get('termo', '').lower()
    resultados = {k: v for k, v in JOGOS_DB.items() if termo in v.titulo.lower()}
    return render_template('dashboard.html', jogos=resultados, usuarios=USUARIOS_DB, comentarios=COMENTARIOS)

# --- Rotas de API para AJAX ---
@app.route('/api/reviews/usuario/<email>')
def api_reviews_usuario(email):
    """Retorna reviews do usuário em JSON"""
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
    """Retorna biblioteca do usuário em JSON"""
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
    """Retorna lista de amigos em JSON"""
    amigos = GerenciadorAmigos.obter_amigos(email)
    amigos_data = []
    for amigo_email in amigos:
        user = USUARIOS_DB.get(amigo_email)
        if user:
            amigos_data.append({
                'email': amigo_email,
                'nome': user.nome
            })
    return jsonify({'amigos': amigos_data})

if __name__ == '__main__':
    app.run(debug=True)