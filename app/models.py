from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db

STATUS = ["AGUARDANDO_APROVACAO", "AGUARDANDO_ENVIO_COTACAO", "AGUARDANDO_RECEBIMENTO_COTACAO",
          "AGUARDANDO_DEFINICAO_FORNECEDOR", "AGUARDANDO_CHEGADA", "CONCLUIDO", "CANCELADA"]
STATUS_LABEL = {
    "AGUARDANDO_APROVACAO": "Aguardando aprovação", "AGUARDANDO_ENVIO_COTACAO": "Aguardando envio p/ cotação",
    "AGUARDANDO_RECEBIMENTO_COTACAO": "Aguardando recebimento da cotação",
    "AGUARDANDO_DEFINICAO_FORNECEDOR": "Aguardando definição de fornecedor",
    "AGUARDANDO_CHEGADA": "Aguardando chegada", "CONCLUIDO": "Concluído", "CANCELADA": "Cancelada"}
# Padrão do painel: tudo menos finalizados
STATUS_PADRAO = [s for s in STATUS if s not in ("CONCLUIDO", "CANCELADA")]

fornecedor_tipo = db.Table("fornecedor_tipo",
    db.Column("fornecedor_id", db.ForeignKey("fornecedores.id"), primary_key=True),
    db.Column("tipo_material_id", db.ForeignKey("tipos_material.id"), primary_key=True))

# Fornecedores removidos de uma solicitação específica (ex.: "não tem o item") — item 90
solicitacao_fornecedor_excluido = db.Table("solicitacao_fornecedor_excluido",
    db.Column("solicitacao_id", db.ForeignKey("solicitacoes.id"), primary_key=True),
    db.Column("fornecedor_id", db.ForeignKey("fornecedores.id"), primary_key=True))


class Empresa(db.Model):
    __tablename__ = "empresas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="solicitante")  # solicitante|almoxarifado|visualizador|admin
    empresa_id = db.Column(db.ForeignKey("empresas.id"))
    senha_temporaria = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    empresa = db.relationship("Empresa")
    solicitacoes = db.relationship("Solicitacao", backref="solicitante",
                                   foreign_keys="Solicitacao.solicitante_id", lazy=True)

    def set_senha(self, s): self.senha_hash = generate_password_hash(s)
    def check_senha(self, s): return check_password_hash(self.senha_hash, s)
    @property
    def is_admin(self): return self.papel == "admin"
    @property
    def is_almox(self): return self.papel == "almoxarifado"
    @property
    def is_viewer(self): return self.papel == "visualizador"
    @property
    def pode_solicitar(self): return self.papel in ("solicitante", "almoxarifado")


class TipoMaterial(db.Model):
    __tablename__ = "tipos_material"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    fornecedores = db.relationship("Fornecedor", secondary=fornecedor_tipo, back_populates="tipos")


class Atividade(db.Model):
    __tablename__ = "atividades"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class Cidade(db.Model):
    __tablename__ = "cidades"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    uf = db.Column(db.String(2))
    ativo = db.Column(db.Boolean, default=True)

    @property
    def rotulo(self):
        return f"{self.nome}/{self.uf}" if self.uf else self.nome


class Transportadora(db.Model):
    __tablename__ = "transportadoras"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class Fornecedor(db.Model):
    __tablename__ = "fornecedores"
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(160))
    nome_fantasia = db.Column(db.String(160))
    email = db.Column(db.String(180), nullable=False)
    contato_nome = db.Column(db.String(120))
    telefone = db.Column(db.String(40))
    telefone_e164 = db.Column(db.String(20))
    usa_email = db.Column(db.Boolean, default=True)   # se o contato é por e-mail
    ativo = db.Column(db.Boolean, default=True)
    tipos = db.relationship("TipoMaterial", secondary=fornecedor_tipo, back_populates="fornecedores")

    @property
    def nome(self): return self.nome_fantasia or self.razao_social or self.email


class Solicitacao(db.Model):
    __tablename__ = "solicitacoes"
    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.ForeignKey("usuarios.id"), nullable=False)
    tipo_material_id = db.Column(db.ForeignKey("tipos_material.id"))
    material = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    fabricante = db.Column(db.String(120))
    link_similar = db.Column(db.Text)
    local_servico = db.Column(db.String(200))   # local de uso / frente de serviço
    status = db.Column(db.String(40), nullable=False, default="AGUARDANDO_APROVACAO")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    quantidade_original = db.Column(db.Integer)
    quantidade_alterada_por = db.Column(db.ForeignKey("usuarios.id"))
    quantidade_alterada_em = db.Column(db.DateTime)
    quantidade_recebida = db.Column(db.Integer, default=0)   # chegada parcial acumulada

    prazo_cotacao = db.Column(db.Date)   # data-limite p/ retorno da cotação (item 93)
    fornecedor_definido_id = db.Column(db.ForeignKey("fornecedores.id"))
    frete_tipo = db.Column(db.String(10))
    frete_modalidade = db.Column(db.String(20))
    transportadora_id = db.Column(db.ForeignKey("transportadoras.id"))
    cidade_retirada_id = db.Column(db.ForeignKey("cidades.id"))
    prazo_recebimento = db.Column(db.Date)
    chegada_confirmada_por = db.Column(db.ForeignKey("usuarios.id"))
    chegada_em = db.Column(db.DateTime)

    tipo = db.relationship("TipoMaterial")
    editor_qtd = db.relationship("Usuario", foreign_keys=[quantidade_alterada_por])
    fornecedor_definido = db.relationship("Fornecedor", foreign_keys=[fornecedor_definido_id])
    transportadora = db.relationship("Transportadora")
    cidade_retirada = db.relationship("Cidade")
    imagens = db.relationship("Imagem", backref="solicitacao", lazy=True, cascade="all, delete-orphan")
    comentarios = db.relationship("Comentario", backref="solicitacao", lazy=True, cascade="all, delete-orphan")
    orcamentos = db.relationship("Orcamento", backref="solicitacao", lazy=True, cascade="all, delete-orphan")
    logs = db.relationship("LogSolicitacao", backref="solicitacao", lazy=True, cascade="all, delete-orphan",
                           order_by="LogSolicitacao.criado_em")
    fornecedores_excluidos = db.relationship("Fornecedor", secondary=solicitacao_fornecedor_excluido)

    @property
    def status_label(self): return STATUS_LABEL.get(self.status, self.status)

    @property
    def cotacao_vencida(self):
        from datetime import date as _d
        return bool(self.status == "AGUARDANDO_RECEBIMENTO_COTACAO"
                    and self.prazo_cotacao and self.prazo_cotacao < _d.today())

    @property
    def chegada_atrasada(self):
        from datetime import date as _d
        return bool(self.status == "AGUARDANDO_CHEGADA"
                    and self.prazo_recebimento and self.prazo_recebimento < _d.today())


class Imagem(db.Model):
    __tablename__ = "imagens"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Comentario(db.Model):
    __tablename__ = "comentarios"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    autor_id = db.Column(db.ForeignKey("usuarios.id"), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    autor = db.relationship("Usuario")


class PedidoCompra(db.Model):
    __tablename__ = "pedidos_compra"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    enviado_em = db.Column(db.DateTime, default=datetime.utcnow)
    enviado_por = db.Column(db.ForeignKey("usuarios.id"))
    destinatarios = db.Column(db.String(1000))
    cotacao_seq = db.Column(db.String(20))   # sequencial da cotação (ex.: COT-2026-001)
    solicitacao = db.relationship("Solicitacao")


class Orcamento(db.Model):
    __tablename__ = "orcamentos"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"), nullable=False)
    valor_total = db.Column(db.Numeric(12, 2), nullable=False)
    moeda = db.Column(db.String(5), default="BRL")
    prazo_entrega = db.Column(db.String(80))
    condicoes_pagamento = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    item_fornecedor = db.Column(db.String(300))   # nome do item como o fornecedor descreveu
    anexo_url = db.Column(db.String(500))
    escolhido = db.Column(db.Boolean, default=False)
    registrado_por = db.Column(db.ForeignKey("usuarios.id"))
    recebido_em = db.Column(db.DateTime, default=datetime.utcnow)
    fornecedor = db.relationship("Fornecedor")


class Notinha(db.Model):
    __tablename__ = "notinhas"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    competencia = db.Column(db.String(7))   # "AAAA-MM" (mês de referência)
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"), nullable=False)
    atividade_id = db.Column(db.ForeignKey("atividades.id"))
    valor = db.Column(db.Numeric(12, 2), nullable=False)
    criado_por = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    fornecedor = db.relationship("Fornecedor")
    atividade = db.relationship("Atividade")


class LogSolicitacao(db.Model):
    __tablename__ = "logs_solicitacao"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    evento = db.Column(db.String(300), nullable=False)
    autor_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    autor = db.relationship("Usuario")


class Sugestao(db.Model):
    __tablename__ = "sugestoes"
    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.ForeignKey("usuarios.id"))
    texto = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    autor = db.relationship("Usuario")
