from flask import Flask, render_template, request, redirect, url_for, flash, session
from modelos.usuario import Usuario, Admin, USUARIOS_DB
from modelos.jogo import Jogo, Categoria, JOGOS_DB
from excecao import GameLinkException, AutenticacaoError

app = Flask(__name__)
app.secret_key = "super_secret_key_gamelink"

# Carga inicial de dados simulados
if not JOGOS_DB:
    # Criando categorias
    c1 = Categoria(1, "RPG")
    c2 = Categoria(2, "Ação")
    
    # Criando jogos
    j1 = Jogo(1, "The Witcher 3", "RPG", "CD Projekt Red", 2015)
    j1.associar_categoria(c1)
    j2 = Jogo(2, "Elden Ring", "RPG", "FromSoftware", 2022)
    j2.associar_categoria(c1)
    j3 = Jogo(3, "GTA V", "Ação", "Rockstar", 2013)
    j3.associar_categoria(c2)
    
    JOGOS_DB[1] = j1
    JOGOS_DB[2] = j2
    JOGOS_DB[3] = j3

    # Conta Admin padrão
    USUARIOS_DB["admin@gamelink.com"] = Admin(1, "Boss", "admin@gamelink.com", "admin123", nivel_acesso=5)

# Rotas de Autenticação

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
            novo_id = len(USUARIOS_DB) + 1
            USUARIOS_DB[email] = Usuario(novo_id, nome, email, senha)
            flash("Cadastro realizado com sucesso! Faça login.", "success")
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
            session['is_admin'] = isinstance(user, Admin) # Checagem de tipo POO
            flash(f"Bem-vindo de volta, {user.nome}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Credenciais inválidas.", "danger")
    return render_template('login.html')

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form['email']
        user = USUARIOS_DB.get(email)
        if user:
            user.token_recuperacao = "123XYZ" # Simulando envio por e-mail
            flash(f"Token de recuperação enviado para o e-mail {email}. (Use o Token: 123XYZ)", "info")
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Rotas de Jogos e Dashboard 

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', jogos=JOGOS_DB.values())

@app.route('/jogos/novo', methods=['POST'])
def novo_jogo():
    if not session.get('is_admin'):
        flash("Apenas administradores podem cadastrar jogos novos.", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        titulo = request.form['titulo']
        genero = request.form['genero']
        desenvolvedora = request.form['desenvolvedora']
        ano = int(request.form['ano'])
        
        novo_id = max(JOGOS_DB.keys(), default=0) + 1
        JOGOS_DB[novo_id] = Jogo(novo_id, titulo, genero, desenvolvedora, ano)
        flash("Jogo cadastrado com sucesso!", "success")
    except ValueError:
        flash("Ano inválido.", "danger")
    return redirect(url_for('dashboard'))

@app.route('/jogos/deletar/<int:id>')
def deletar_jogo(id):
    if not session.get('is_admin'):
        flash("Permissão negada.", "danger")
        return redirect(url_for('dashboard'))
    
    if id in JOGOS_DB:
        del JOGOS_DB[id]
        flash("Jogo removido com sucesso!", "success")
    return redirect(url_for('dashboard'))

@app.route('/busca', methods=['GET'])
def busca():
    termo = request.args.get('termo', '').lower()
    filtro = request.args.get('filtro', 'titulo')
    resultados = []

    for jogo in JOGOS_DB.values():
        if filtro == 'titulo' and termo in jogo.titulo.lower():
            resultados.append(jogo)
        elif filtro == 'genero' and termo in jogo.genero.lower():
            resultados.append(jogo)
            
    return render_template('dashboard.html', jogos=resultados, busca_termo=termo)

if __name__ == '__main__':
    app.run(debug=True)