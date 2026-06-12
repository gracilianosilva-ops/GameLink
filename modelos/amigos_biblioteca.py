from datetime import datetime
from modelos.base import EntidadeBase
from excecao import OperacaoInvalidaError

# Banco de dados simulado para amigos, biblioteca e reviews
AMIZADES_DB = {}  # email1_email2: {'email1': str, 'email2': str, 'status': 'pendente'/'aceito', 'data': datetime}
BIBLIOTECA_DB = {}  # email_jogo_id: {'email': str, 'jogo_id': int, 'data_adicao': datetime, 'tempo_jogado': int}
REVIEWS_DB = {}  # review_id: Review object
NOTIFICACOES_DB = {}  # email: [notificacoes]


class SolicitacaoAmizade(EntidadeBase):
    """Classe para gerenciar solicitações de amizade"""
    def __init__(self, id_entidade: int, email_solicitante: str, email_receptor: str):
        super().__init__(id_entidade)
        self.email_solicitante = email_solicitante
        self.email_receptor = email_receptor
        self.status = 'pendente'  # pendente, aceito, recusado
        self.data_solicitacao = datetime.now()

    def aceitar(self):
        self.status = 'aceito'
        self.data_aceito = datetime.now()

    def recusar(self):
        self.status = 'recusado'

    def obter_resumo(self) -> str:
        return f"Solicitação de {self.email_solicitante} para {self.email_receptor}: {self.status}"


class BibliotecaJogo(EntidadeBase):
    """Classe para armazenar informações do jogo na biblioteca do usuário"""
    def __init__(self, id_entidade: int, email_usuario: str, jogo_id: int):
        super().__init__(id_entidade)
        self.email_usuario = email_usuario
        self.jogo_id = jogo_id
        self.data_adicao = datetime.now()
        self.tempo_jogado_horas = 0  # Horas jogadas
        self.concluido = False
        self.platinado = False  # Se conquistou todas as conquistas

    def atualizar_tempo_jogado(self, horas: int):
        """Atualiza tempo jogado"""
        if horas >= 0:
            self.tempo_jogado_horas = horas
        else:
            raise OperacaoInvalidaError("Tempo jogado não pode ser negativo")

    def marcar_concluido(self):
        self.concluido = True

    def marcar_platinado(self):
        self.platinado = True
        self.concluido = True

    def obter_resumo(self) -> str:
        status = "Platinado" if self.platinado else ("Concluído" if self.concluido else "Jogando")
        return f"{self.email_usuario} - Jogo {self.jogo_id}: {status} ({self.tempo_jogado_horas}h)"


class Review(EntidadeBase):
    """Classe para avaliações/reviews de jogos"""
    def __init__(self, id_entidade: int, jogo_id: int, email_usuario: str, titulo: str, conteudo: str, nota: int):
        super().__init__(id_entidade)
        self.jogo_id = jogo_id
        self.email_usuario = email_usuario
        self.titulo = titulo
        self.conteudo = conteudo
        self.nota = max(1, min(nota, 10))  # Garante nota entre 1-10
        self.data_criacao = datetime.now()
        self.visivel = True
        self.curtidas = 0  # Quantidade de pessoas que acharam útil

    def atualizar_nota(self, nova_nota: int):
        self.nota = max(1, min(nova_nota, 10))

    def atualizar_conteudo(self, novo_titulo: str, novo_conteudo: str):
        self.titulo = novo_titulo
        self.conteudo = novo_conteudo

    def adicionar_curtida(self):
        self.curtidas += 1

    def remover_curtida(self):
        if self.curtidas > 0:
            self.curtidas -= 1

    def obter_resumo(self) -> str:
        return f"Review: {self.titulo} ({self.nota}/10) por {self.email_usuario}"


class Notificacao(EntidadeBase):
    """Classe para notificações de atividades"""
    def __init__(self, id_entidade: int, email_receptor: str, tipo: str, titulo: str, descricao: str, link: str = None):
        super().__init__(id_entidade)
        self.email_receptor = email_receptor
        self.tipo = tipo  # 'post', 'amizade', 'amigo_post', 'novo_jogo'
        self.titulo = titulo
        self.descricao = descricao
        self.link = link
        self.data_criacao = datetime.now()
        self.lida = False

    def marcar_como_lida(self):
        self.lida = True

    def obter_resumo(self) -> str:
        status = "Lida" if self.lida else "Não lida"
        return f"Notificação ({self.tipo}): {self.titulo} - {status}"


class GerenciadorAmigos:
    """Classe para gerenciar sistema de amizade"""
    
    @staticmethod
    def enviar_solicitacao(id_solicitacao: int, email_solicitante: str, email_receptor: str) -> SolicitacaoAmizade:
        """Envia uma solicitação de amizade"""
        chave = f"{min(email_solicitante, email_receptor)}_{max(email_solicitante, email_receptor)}"
        if chave in AMIZADES_DB:
            raise OperacaoInvalidaError("Já existe uma solicitação entre esses usuários")
        
        solicitacao = SolicitacaoAmizade(id_solicitacao, email_solicitante, email_receptor)
        AMIZADES_DB[chave] = solicitacao
        return solicitacao

    @staticmethod
    def aceitar_solicitacao(email1: str, email2: str):
        """Aceita uma solicitação de amizade"""
        chave = f"{min(email1, email2)}_{max(email1, email2)}"
        if chave in AMIZADES_DB:
            AMIZADES_DB[chave].aceitar()
        else:
            raise OperacaoInvalidaError("Solicitação não encontrada")

    @staticmethod
    def recusar_solicitacao(email1: str, email2: str):
        """Recusa uma solicitação de amizade"""
        chave = f"{min(email1, email2)}_{max(email1, email2)}"
        if chave in AMIZADES_DB:
            AMIZADES_DB[chave].recusar()
        else:
            raise OperacaoInvalidaError("Solicitação não encontrada")

    @staticmethod
    def obter_amigos(email: str) -> list:
        """Retorna lista de amigos aceitos"""
        amigos = []
        for chave, amizade in AMIZADES_DB.items():
            if amizade.status == 'aceito':
                if amizade.email_solicitante == email:
                    amigos.append(amizade.email_receptor)
                elif amizade.email_receptor == email:
                    amigos.append(amizade.email_solicitante)
        return amigos

    @staticmethod
    def obter_solicitacoes_pendentes(email: str) -> list:
        """Retorna solicitações pendentes para o usuário"""
        solicitacoes = []
        for chave, amizade in AMIZADES_DB.items():
            if amizade.status == 'pendente' and amizade.email_receptor == email:
                solicitacoes.append(amizade)
        return solicitacoes

    @staticmethod
    def sao_amigos(email1: str, email2: str) -> bool:
        """Verifica se dois usuários são amigos"""
        chave = f"{min(email1, email2)}_{max(email1, email2)}"
        amizade = AMIZADES_DB.get(chave)
        return amizade is not None and amizade.status == 'aceito'


class GerenciadorBiblioteca:
    """Classe para gerenciar biblioteca pessoal de jogos"""
    
    @staticmethod
    def adicionar_jogo(id_biblioteca: int, email: str, jogo_id: int) -> BibliotecaJogo:
        """Adiciona jogo à biblioteca"""
        chave = f"{email}_{jogo_id}"
        if chave in BIBLIOTECA_DB:
            raise OperacaoInvalidaError("Jogo já está na biblioteca")
        
        biblioteca = BibliotecaJogo(id_biblioteca, email, jogo_id)
        BIBLIOTECA_DB[chave] = biblioteca
        return biblioteca

    @staticmethod
    def remover_jogo(email: str, jogo_id: int):
        """Remove jogo da biblioteca"""
        chave = f"{email}_{jogo_id}"
        if chave in BIBLIOTECA_DB:
            del BIBLIOTECA_DB[chave]
        else:
            raise OperacaoInvalidaError("Jogo não encontrado na biblioteca")

    @staticmethod
    def obter_biblioteca(email: str) -> list:
        """Retorna todos os jogos na biblioteca do usuário"""
        jogos = []
        for chave, biblioteca in BIBLIOTECA_DB.items():
            if biblioteca.email_usuario == email:
                jogos.append(biblioteca)
        return jogos

    @staticmethod
    def jogo_na_biblioteca(email: str, jogo_id: int) -> bool:
        """Verifica se jogo está na biblioteca"""
        chave = f"{email}_{jogo_id}"
        return chave in BIBLIOTECA_DB


class GerenciadorReviews:
    """Classe para gerenciar reviews de jogos"""
    
    @staticmethod
    def criar_review(id_review: int, jogo_id: int, email: str, titulo: str, conteudo: str, nota: int) -> Review:
        """Cria um novo review"""
        review = Review(id_review, jogo_id, email, titulo, conteudo, nota)
        REVIEWS_DB[id_review] = review
        return review

    @staticmethod
    def obter_reviews_jogo(jogo_id: int) -> list:
        """Retorna todos os reviews de um jogo"""
        reviews = [r for r in REVIEWS_DB.values() if r.jogo_id == jogo_id and r.visivel]
        return sorted(reviews, key=lambda x: x.curtidas, reverse=True)

    @staticmethod
    def obter_reviews_usuario(email: str) -> list:
        """Retorna todos os reviews de um usuário"""
        reviews = [r for r in REVIEWS_DB.values() if r.email_usuario == email]
        return sorted(reviews, key=lambda x: x.data_criacao, reverse=True)

    @staticmethod
    def deletar_review(review_id: int):
        """Deleta um review (soft delete)"""
        if review_id in REVIEWS_DB:
            REVIEWS_DB[review_id].visivel = False
        else:
            raise OperacaoInvalidaError("Review não encontrado")

    @staticmethod
    def obter_media_nota_jogo(jogo_id: int) -> float:
        """Calcula a nota média de um jogo"""
        reviews = GerenciadorReviews.obter_reviews_jogo(jogo_id)
        if not reviews:
            return 0
        return sum(r.nota for r in reviews) / len(reviews)


class GerenciadorNotificacoes:
    """Classe para gerenciar notificações"""
    
    @staticmethod
    def criar_notificacao(id_notif: int, email_receptor: str, tipo: str, titulo: str, descricao: str, link: str = None):
        """Cria uma notificação"""
        notif = Notificacao(id_notif, email_receptor, tipo, titulo, descricao, link)
        if email_receptor not in NOTIFICACOES_DB:
            NOTIFICACOES_DB[email_receptor] = []
        NOTIFICACOES_DB[email_receptor].append(notif)
        return notif

    @staticmethod
    def obter_notificacoes(email: str, nao_lidas_apenas: bool = False) -> list:
        """Retorna notificações do usuário"""
        notificacoes = NOTIFICACOES_DB.get(email, [])
        if nao_lidas_apenas:
            return [n for n in notificacoes if not n.lida]
        return sorted(notificacoes, key=lambda x: x.data_criacao, reverse=True)

    @staticmethod
    def marcar_como_lida(email: str, notif_id: int):
        """Marca uma notificação como lida"""
        notificacoes = NOTIFICACOES_DB.get(email, [])
        for n in notificacoes:
            if n.id == notif_id:
                n.marcar_como_lida()
                break

    @staticmethod
    def contar_nao_lidas(email: str) -> int:
        """Conta notificações não lidas"""
        return len(GerenciadorNotificacoes.obter_notificacoes(email, nao_lidas_apenas=True))

    @staticmethod
    def notificar_novo_post(email_receptor: str, titulo: str, descricao: str, post_id: int, id_notif: int):
        """Notifica novo post de um amigo"""
        GerenciadorNotificacoes.criar_notificacao(
            id_notif, 
            email_receptor, 
            'amigo_post',
            f"📝 Novo post",
            descricao,
            f"/posts/{post_id}"
        )
