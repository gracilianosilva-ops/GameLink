# GameLink

## Visão Geral
GameLink é uma plataforma web voltada para jogadores, com funcionalidades de cadastro, perfil, biblioteca de jogos, posts, amizades, reviews e notificações. O projeto foi organizado em módulos para reforçar a abordagem orientada a objetos.

## Requisitos atendidos
- Mínimo de 10 classes concretas: o projeto conta com classes como Usuario, Admin, Jogo, Categoria, Post, Comentario, SolicitaçãoAmizade, BibliotecaJogo, Review, ComentarioReview, Notificacao, Mensagem e PerfilJogador.
- Herança: Usuario herda de EntidadeBase e Admin herda de Usuario.
- Encapsulamento: atributos privados e protegidos são usados em classes como Usuario e PerfilJogador.
- Tratamento de exceções: exceções personalizadas em excecao.py para autenticação e operações inválidas.
- Modularização: o código está organizado em módulos e pacotes dentro da pasta modelos.

## Estrutura do projeto
- app.py: aplicação Flask principal.
- modelos/: classes de domínio e regras de negócio.
- database.py: inicialização do banco de dados.
- templates/: interfaces web.
- static/: arquivos estáticos.

## Como executar
1. Entre na pasta do projeto.
2. Crie ou ative um ambiente virtual.
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Inicie a aplicação:
   ```bash
   python app.py
   ```
5. Acesse http://127.0.0.1:5000.

## Variáveis de e-mail
Para ativar o envio real de e-mails, configure:
- MAIL_HOST
- MAIL_PORT
- MAIL_USERNAME
- MAIL_PASSWORD
- MAIL_FROM
- MAIL_USE_TLS
- MAIL_USE_SSL

Se não forem configuradas, o sistema entra em modo local de teste e exibe o código de verificação na tela.
