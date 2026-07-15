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

# Unidades de medida (item 117) — lista fixa, sem necessidade de cadastro.
UNIDADES_MEDIDA = ["UN", "KG", "G", "L", "ML", "M", "M²", "M³", "CX", "PAR", "ROLO", "PCT", "SC", "CJ"]

# Item 145 — listas fixas do Relatório de Carga (com opção "Outro" no formulário)
TIPOS_VOLUME = ["Pallets", "Caixas de madeira", "Caixas de papelão", "Tambores",
                "Sacos/Bags", "Fardos", "Amarrados", "Bobinas", "Engradados", "Volume avulso"]
NATUREZAS_OPERACAO = ["Venda de Mercadoria", "Remessa para Conserto", "Remessa para Industrialização",
                      "Devolução", "Transferência", "Uso e Consumo", "Bonificação", "Comodato", "Garantia"]

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
    # item 150: novo vínculo para a tabela unificada (fornecedores com is_empresa_interna).
    # empresa_id antigo é mantido para não quebrar nada; a migração popula este a partir daquele.
    empresa_fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"))
    senha_temporaria = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    is_master = db.Column(db.Boolean, default=False)   # ADMIN MASTER (único; protegido)
    tema_preferido = db.Column(db.String(10), default="escuro")   # 'claro' | 'escuro' — item 113
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    empresa = db.relationship("Empresa")
    empresa_fornecedor = db.relationship("Fornecedor", foreign_keys=[empresa_fornecedor_id])
    solicitacoes = db.relationship("Solicitacao", backref="solicitante",
                                   foreign_keys="Solicitacao.solicitante_id", lazy=True)

    def set_senha(self, s): self.senha_hash = generate_password_hash(s)
    def check_senha(self, s): return check_password_hash(self.senha_hash, s)
    def get_id(self): return f"U:{self.id}"
    @property
    def is_admin(self): return self.papel == "admin"

    def pode_gerir(self, alvo):
        """Regras de hierarquia (Etapa 2.5):
        - Precisa ser admin para gerir alguém.
        - Admin simples faz tudo, EXCETO editar/desativar o MASTER ou outros ADMINS.
        - Só o MASTER edita/desativa admins.
        - Ninguém desativa/rebaixa o MASTER (tratado à parte na edição)."""
        if not self.is_admin:
            return False
        if alvo.is_master:
            return bool(self.is_master)         # só o próprio master mexe no master (limitado)
        if alvo.papel == "admin":
            return bool(self.is_master)         # só master mexe em admins
        return True                              # admin comum gere não-admins
    @property
    def is_almox(self): return self.papel == "almoxarifado"
    @property
    def is_viewer(self): return self.papel == "visualizador"
    @property
    def pode_solicitar(self): return self.papel in ("solicitante", "almoxarifado")

    # ---- Módulo Almoxarifado (Chaves / Extintores / Colaboradores + tópicos em construção) ----
    @property
    def pode_almox_modulo(self):
        """Quem enxerga o módulo Almoxarifado."""
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_chaves(self):
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_extintores(self):
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_colaboradores(self):
        return self.papel in ("admin", "almoxarifado")


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
    cnpj = db.Column(db.String(20))          # item 145 — só números, formatado na exibição
    endereco = db.Column(db.String(255))     # item 145
    aprovacao = db.Column(db.String(12), default="aprovado")  # 'aprovado' | 'pendente' (item 145)
    ativo = db.Column(db.Boolean, default=True)


class Fornecedor(db.Model):
    __tablename__ = "fornecedores"
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(160))
    nome_fantasia = db.Column(db.String(160))
    email = db.Column(db.String(180))  # pode ser nulo em cadastro pendente vindo do relatório (item 145)
    contato_nome = db.Column(db.String(120))
    telefone = db.Column(db.String(40))
    telefone_e164 = db.Column(db.String(20))
    cnpj = db.Column(db.String(20))                  # item 145 — só números, formatado na exibição
    inscricao_estadual = db.Column(db.String(20))    # item 145
    endereco = db.Column(db.String(255))             # item 145 — endereço antigo (texto livre); mantido como fallback
    # Endereço estruturado (item 150)
    cep = db.Column(db.String(9))
    logradouro = db.Column(db.String(180))
    numero = db.Column(db.String(20))
    bairro = db.Column(db.String(120))
    complemento = db.Column(db.String(120))
    cidade = db.Column(db.String(120))
    estado = db.Column(db.String(2))
    # Papel no cadastro unificado (item 150): pode ser fornecedor, empresa interna, ou ambos
    is_fornecedor = db.Column(db.Boolean, default=True)
    is_empresa_interna = db.Column(db.Boolean, default=False)
    aprovacao = db.Column(db.String(12), default="aprovado")  # 'aprovado' | 'pendente' (item 145)
    usa_email = db.Column(db.Boolean, default=True)   # se o contato é por e-mail
    ativo = db.Column(db.Boolean, default=True)
    tipos = db.relationship("TipoMaterial", secondary=fornecedor_tipo, back_populates="fornecedores")

    @property
    def nome(self): return self.nome_fantasia or self.razao_social or self.email

    @property
    def aprovado(self):
        return (self.aprovacao or "aprovado") == "aprovado"

    @property
    def endereco_completo(self):
        """Monta o endereço a partir dos campos estruturados; cai no texto antigo se vazios."""
        partes = []
        if self.logradouro:
            linha = self.logradouro
            if self.numero:
                linha += f", {self.numero}"
            partes.append(linha)
        if self.bairro:
            partes.append(self.bairro)
        if self.complemento:
            partes.append(self.complemento)
        cidade_uf = " - ".join(x for x in [self.cidade, self.estado] if x)
        if cidade_uf:
            partes.append(cidade_uf)
        if self.cep:
            partes.append(f"CEP {self.cep}")
        if partes:
            return ", ".join(partes)
        return self.endereco or ""

    @property
    def cadastro_incompleto(self):
        """Sem CNPJ = cadastro antigo a completar (item 150 — gera aviso no sininho)."""
        return not (self.cnpj or "").strip()


class Solicitacao(db.Model):
    __tablename__ = "solicitacoes"
    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.ForeignKey("usuarios.id"), nullable=False)
    tipo_material_id = db.Column(db.ForeignKey("tipos_material.id"))
    material = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    unidade_medida = db.Column(db.String(10))   # item 117 — lista fixa em UNIDADES_MEDIDA
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


# ==================== MÓDULO ALMOXARIFADO (item novo) ====================
# Tabelas de apoio ao módulo Chaves / Extintores / Colaboradores.
# Criadas por db.create_all(); colunas novas entram pelo _light_migrate().

class QuadroChave(db.Model):
    """Localizador das chaves (item roadmap §4). Lista própria e pesquisável."""
    __tablename__ = "almox_quadros_chave"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Chave(db.Model):
    __tablename__ = "almox_chaves"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30))          # legado — não usado nas telas novas
    descricao = db.Column(db.String(160), nullable=False)
    local = db.Column(db.String(120))          # legado — substituído por quadro_chave_id
    quadro_chave_id = db.Column(db.ForeignKey("almox_quadros_chave.id"))
    qr_uid = db.Column(db.String(20), unique=True)   # identificador do QR individual da chave
    status = db.Column(db.String(20), default="Disponível")   # Disponível | Em uso
    com_quem = db.Column(db.String(160))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    quadro = db.relationship("QuadroChave")

    @property
    def quadro_nome(self):
        return self.quadro.nome if self.quadro else (self.local or "—")


class Extintor(db.Model):
    __tablename__ = "almox_extintores"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30))
    predio = db.Column(db.String(40))            # SEPN | DELTA3 | DELTA6 | MIR | UNIT
    local = db.Column(db.String(120))            # Local de instalação
    tipo = db.Column(db.String(40))              # TIPO/CARGA (ex.: PQS - 06KG)
    classe = db.Column(db.String(10))            # ABC | BC ...
    validade = db.Column(db.Date)                # validade da CARGA (competência)
    teste_hidrostatico = db.Column(db.Date)      # validade do TESTE HIDROSTÁTICO (competência)
    inspecao = db.Column(db.Date)
    status = db.Column(db.String(20), default="No Local")   # legado
    situacao = db.Column(db.String(20), default="NO_PRAZO")  # NO_PRAZO|IRREGULAR|EM_RECARGA|PRONTO_REPO (PROX/VENCIDO derivados das datas)
    qr_uid = db.Column(db.String(20), unique=True)
    retirado_por = db.Column(db.String(160))     # quem retirou p/ recarga (repõe depois)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class LocalAlmox(db.Model):
    """Local de estocagem (prateleira/armazém). Um deles é a Estocagem Temporária."""
    __tablename__ = "almox_locais"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    temporaria = db.Column(db.Boolean, default=False)   # local padrão de entrada/devolução
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ProdutoAlmox(db.Model):
    """Item de estoque com quantidade (entrada/saída/saldo) e um local atual."""
    __tablename__ = "almox_produtos"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40))
    nome = db.Column(db.String(160), nullable=False)
    unidade = db.Column(db.String(12), default="UN")
    categoria = db.Column(db.String(80))
    saldo = db.Column(db.Float, default=0)
    saldo_minimo = db.Column(db.Float, default=0)
    local_id = db.Column(db.ForeignKey("almox_locais.id"))
    qr_uid = db.Column(db.String(20), unique=True)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship("LocalAlmox")

    @property
    def abaixo_minimo(self):
        return self.saldo_minimo and self.saldo <= self.saldo_minimo

    @property
    def local_nome(self):
        return self.local.nome if self.local else "—"


class MovimentacaoMaterial(db.Model):
    """Histórico de entrada/saída/ajuste/movimentação/inventário de material."""
    __tablename__ = "almox_mov_material"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"))
    produto_nome = db.Column(db.String(160))
    tipo = db.Column(db.String(14))               # entrada | saida | ajuste | movimentacao | inventario
    quantidade = db.Column(db.Float)
    saldo_apos = db.Column(db.Float)
    local_de = db.Column(db.String(120))          # movimentação: origem
    local_para = db.Column(db.String(120))        # movimentação: destino
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    colaborador_nome = db.Column(db.String(160))
    operador_id = db.Column(db.ForeignKey("usuarios.id"))
    obs = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    operador = db.relationship("Usuario")


class InspecaoExtintor(db.Model):
    """Registro de inspeção / conferência / reposição no local do extintor."""
    __tablename__ = "almox_insp_extintor"
    id = db.Column(db.Integer, primary_key=True)
    extintor_id = db.Column(db.ForeignKey("almox_extintores.id"))
    extintor_cod = db.Column(db.String(30))
    tipo = db.Column(db.String(20))               # inspecao | conferencia | reposto_local | retirada | reposicao
    resultado = db.Column(db.String(20))          # conforme | irregular
    itens_json = db.Column(db.Text)               # JSON com o resultado de cada item do checklist
    etiqueta_ok = db.Column(db.Boolean)           # item exclusivo do Almoxarifado (None = não se aplica)
    obs = db.Column(db.Text)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    colaborador_nome = db.Column(db.String(160))  # quem inspecionou (campo) ou operou
    operador_id = db.Column(db.ForeignKey("usuarios.id"))  # se feito por usuário logado (desktop)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class PendenciaEtiqueta(db.Model):
    """Pendência de regularização quando 'Colada a etiqueta QR Code?' = Não."""
    __tablename__ = "almox_pend_etiqueta"
    id = db.Column(db.Integer, primary_key=True)
    extintor_id = db.Column(db.ForeignKey("almox_extintores.id"))
    extintor_cod = db.Column(db.String(30))
    predio = db.Column(db.String(40))
    local = db.Column(db.String(120))
    aberta_em = db.Column(db.DateTime, default=datetime.utcnow)
    aberta_por = db.Column(db.String(160))
    resolvida = db.Column(db.Boolean, default=False)
    resolvida_em = db.Column(db.DateTime)
    resolvida_por = db.Column(db.String(160))


# Checklist de inspeção do extintor (10 itens). O item de etiqueta é exclusivo do Almoxarifado.
CHECK_EXTINTOR = [
    "Acesso e sinalização desobstruídos",
    "Lacre e pino de segurança intactos",
    "Manômetro na faixa verde (pressão adequada)",
    "Mangueira, difusor e gatilho sem danos",
    "Cilindro sem corrosão, amassados ou vazamentos",
    "Rótulo / etiqueta de identificação legível",
    "Suporte / fixação em bom estado",
    "Peso / carga aparentemente adequados",
    "Validade da carga vigente",
    "Teste hidrostático dentro do prazo",
]
ITEM_ETIQUETA_EXTINTOR = "Etiqueta grudada e em bom estado?"


# Tarefas que um Papel de colaborador de campo pode ter (a "caixinha").
TAREFAS_COLABORADOR = [
    ("inspecionar_extintor", "Inspecionar extintor"),
    ("retirar_repor_extintor", "Retirar / repor extintor"),
    ("pedir_devolver_chave", "Pedir / devolver chave"),
    ("pegar_devolver_material", "Pegar / devolver material"),
]
TAREFAS_DICT = dict(TAREFAS_COLABORADOR)


class HistoricoColaborador(db.Model):
    """Histórico de alterações no cadastro do colaborador (papel, empresa, cargo)."""
    __tablename__ = "almox_hist_colaborador"
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    colaborador_nome = db.Column(db.String(160))
    campo = db.Column(db.String(20))             # papel | empresa | cargo
    de = db.Column(db.String(160))
    para = db.Column(db.String(160))
    alterado_por_nome = db.Column(db.String(160))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class HistoricoPapel(db.Model):
    """Histórico de troca de papel de acesso (Etapa 2.5). Guarda de/até e quem alterou."""
    __tablename__ = "almox_hist_papel"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    pessoa_nome = db.Column(db.String(160))
    papel = db.Column(db.String(30))
    inicio = db.Column(db.DateTime, default=datetime.utcnow)
    fim = db.Column(db.DateTime)                 # None = vigente
    alterado_por = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    autor = db.relationship("Usuario", foreign_keys=[alterado_por])


class PapelColaborador(db.Model):
    """Papel de colaborador de campo (não loga no sistema). Cada papel tem suas tarefas."""
    __tablename__ = "almox_papeis"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    tarefas = db.Column(db.String(400), default="")   # chaves separadas por vírgula
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def lista_tarefas(self):
        return [t for t in (self.tarefas or "").split(",") if t]

    @property
    def tarefas_rotulos(self):
        return [TAREFAS_DICT.get(t, t) for t in self.lista_tarefas]


class Colaborador(UserMixin, db.Model):
    __tablename__ = "almox_colaboradores"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    cpf = db.Column(db.String(20))
    email = db.Column(db.String(180))        # opcional — permite login por e-mail também
    empresa = db.Column(db.String(160))
    funcao = db.Column(db.String(120))       # legado — mantido; "cargo" é o campo novo
    cargo = db.Column(db.String(120))
    papel = db.Column(db.String(120), default="COLABORADOR DIVERSO")
    qr_uid = db.Column(db.String(20), unique=True)
    senha_hash = db.Column(db.String(255))   # senha de confirmação (coletor), login do extintor e do sistema
    tema_preferido = db.Column(db.String(10), default="escuro")
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, s): self.senha_hash = generate_password_hash(s)
    def check_senha(self, s):
        return bool(self.senha_hash) and check_password_hash(self.senha_hash, s)
    @property
    def tem_senha(self): return bool(self.senha_hash)
    @property
    def cargo_exib(self): return self.cargo or self.funcao or "—"

    # ---- Login no sistema: get_id prefixado p/ conviver com Usuario ----
    def get_id(self): return f"C:{self.id}"

    # ---- Camada de compatibilidade (para as telas não quebrarem) ----
    @property
    def _p(self): return (self.papel or "").strip().lower()
    @property
    def is_admin(self): return self._p == "admin"
    @property
    def is_master(self): return False
    @property
    def is_viewer(self): return False
    @property
    def is_almox(self): return self._p == "almoxarifado"
    @property
    def pode_solicitar(self): return True
    @property
    def senha_temporaria(self): return False
    @property
    def _papel_modulo(self): return self._p in ("admin", "almoxarifado")
    @property
    def pode_almox_modulo(self): return self._papel_modulo
    @property
    def pode_chaves(self): return self._papel_modulo
    @property
    def pode_extintores(self): return self._papel_modulo
    @property
    def pode_colaboradores(self): return self._papel_modulo
    def pode_gerir(self, alvo): return False


class MovimentacaoChave(db.Model):
    """Histórico estruturado de retirada/devolução de chave (coletor e desktop)."""
    __tablename__ = "almox_mov_chaves"
    id = db.Column(db.Integer, primary_key=True)
    chave_id = db.Column(db.ForeignKey("almox_chaves.id"))
    chave_desc = db.Column(db.String(160))       # snapshot da descrição
    quadro_nome = db.Column(db.String(160))       # snapshot do quadro (localizador)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    colaborador_nome = db.Column(db.String(160))  # snapshot do nome
    acao = db.Column(db.String(12))               # 'retirada' | 'devolucao'
    retirado_por = db.Column(db.String(160))       # em devoluções: quem estava com a chave (pode diferir de quem devolveu)
    operador_id = db.Column(db.ForeignKey("usuarios.id"))   # quem operou (almoxarife/admin)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    operador = db.relationship("Usuario")


class AlmoxLog(db.Model):
    """Log de ações do módulo (chaves, extintores, colaboradores)."""
    __tablename__ = "almox_log"
    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.ForeignKey("usuarios.id"))
    categoria = db.Column(db.String(30))
    detalhe = db.Column(db.String(400))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    autor = db.relationship("Usuario")
