from flask import Flask, render_template, request, redirect, url_for, flash, session
from modelos.usuario import Usuario, Admin, USUARIOS_DB
from modelos.jogo import Jogo, Categoria, JOGOS_DB
from excecao import GameLinkException, AutenticacaoError

app = Flask(__name__)
app.secret_key = "super_secret_key_gamelink"

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
    return render_template('dashboard.html', jogos=JOGOS_DB, usuarios=USUARIOS_DB, comentarios=COMENTARIOS)

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
    if meu_email and meu_email != email_alvo:
        AMIZADES.append((meu_email, email_alvo, 'aceito'))
    return redirect(url_for('dashboard'))

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/busca')
def busca():
    termo = request.args.get('termo', '').lower()
    resultados = {k: v for k, v in JOGOS_DB.items() if termo in v.titulo.lower()}
    return render_template('dashboard.html', jogos=resultados, usuarios=USUARIOS_DB, comentarios=COMENTARIOS)

if __name__ == '__main__':
    app.run(debug=True)