from modelos.base import EntidadeBase
from excecao import AutenticacaoError

# Banco de dados simulado em memória para este módulo
USUARIOS_DB = {}

class Usuario(EntidadeBase):
    # Classe concreta para usuários comuns
    def __init__(self, id_entidade: int, nome: str, email: str, password: str):
        super().__init__(id_entidade)
        self.nome = nome
        self.email = email
        self.__password = password  # Atributo privado
        self.token_recuperacao = None
        self.idade = None
        self.gosto_jogos = ""  # Descrição dos gostos
        self.telefone = ""

    # Getter e Setter para controle de visibilidade da senha com validação
    def verificar_senha(self, password: str) -> bool:
        return self.__password == password

    def alterar_senha_com_token(self, token: str, nova_senha: str):
        if not self.token_recuperacao or self.token_recuperacao != token:
            raise AutenticacaoError("Token de recuperação inválido ou expirado.")
        self.__password = nova_senha
        self.token_recuperacao = None # Consome o token

    def obter_resumo(self) -> str:
        return f"Jogador: {self.nome} ({self.email})"


class Admin(Usuario):
    # Classe que herda de Usuario
    def __init__(self, id_entidade: int, nome: str, email: str, password: str, nivel_acesso: int = 1):
        super().__init__(id_entidade, nome, email, password)
        self.nivel_acesso = nivel_acesso

    def obter_resumo(self) -> str:
        return f"Administrador: {self.nome} - Nível {self.nivel_acesso}"