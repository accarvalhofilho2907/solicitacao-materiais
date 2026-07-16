from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import event
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
    def pode_material(self):
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

    # Coluna legada 'nome' (NOT NULL no banco antigo). Mantida e preenchida
    # automaticamente a partir de nome_fantasia/razao_social (ver evento abaixo),
    # para o cadastro unificado funcionar sem alterar a estrutura em produção.
    nome = db.Column(db.String(200))

    @property
    def nome_exib(self):
        return self.nome_fantasia or self.razao_social or self.email or self.nome

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
    qr_uid = db.Column(db.String(20), unique=True)   # QR próprio do quadro (QUAD-...)
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
    """Local de estocagem (prateleira/armazém). Um deles é a Estocagem Temporária.
    LEGADO: mantido durante a transição para a hierarquia Planta→Armazém→Localizador."""
    __tablename__ = "almox_locais"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    temporaria = db.Column(db.Boolean, default=False)   # local padrão de entrada/devolução
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Planta(db.Model):
    """Site onde se trabalha (ex.: Delta Maranhão)."""
    __tablename__ = "almox_plantas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Armazem(db.Model):
    """Galpão dentro de uma planta (ex.: Galpão D6)."""
    __tablename__ = "almox_armazens"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    planta = db.relationship("Planta")

    @property
    def planta_nome(self):
        return self.planta.nome if self.planta else "—"


class Localizador(db.Model):
    """Endereço físico: Fila*Estante*Nível (ex.: A*1*3), dentro de um armazém."""
    __tablename__ = "almox_localizadores"
    id = db.Column(db.Integer, primary_key=True)
    armazem_id = db.Column(db.ForeignKey("almox_armazens.id"))
    fila = db.Column(db.String(1))       # uma letra A-Z
    estante = db.Column(db.Integer)      # número
    nivel = db.Column(db.Integer)        # número
    qr_uid = db.Column(db.String(20), unique=True)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    armazem = db.relationship("Armazem")

    __table_args__ = (db.UniqueConstraint("armazem_id", "fila", "estante", "nivel",
                                          name="uq_localizador"),)

    @property
    def codigo(self):
        return f"{self.fila}*{self.estante}*{self.nivel}"

    @property
    def caminho(self):
        a = self.armazem
        p = a.planta_nome if a else "—"
        an = a.nome if a else "—"
        return f"{p} / {an} / {self.codigo}"


class ProdutoAlmox(db.Model):
    """Item de estoque com quantidade (entrada/saída/saldo) e um local atual."""
    __tablename__ = "almox_produtos"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40))
    codigo_barras = db.Column(db.String(60))          # p/ leitura na entrada
    nome = db.Column(db.String(160), nullable=False)
    unidade = db.Column(db.String(12), default="UN")
    categoria = db.Column(db.String(80))
    saldo = db.Column(db.Float, default=0)
    saldo_minimo = db.Column(db.Float, default=0)
    local_id = db.Column(db.ForeignKey("almox_locais.id"))
    localizador_id = db.Column(db.ForeignKey("almox_localizadores.id"))   # novo endereço físico
    fabricante_id = db.Column(db.ForeignKey("almox_fabricantes.id"))      # último fabricante usado
    qr_uid = db.Column(db.String(20), unique=True)
    ativo = db.Column(db.Boolean, default=True)
    pendente_aprovacao = db.Column(db.Boolean, default=False)  # criado na entrada; aguarda admin
    # cadastro-raiz: quais opcionais este item usa (aparecem na entrada/ajuste)
    opc_tag = db.Column(db.Boolean, default=False)
    opc_ca = db.Column(db.Boolean, default=False)
    opc_validade = db.Column(db.Boolean, default=False)
    opc_validade_calib = db.Column(db.Boolean, default=False)
    opc_lote = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    local = db.relationship("LocalAlmox")
    localizador = db.relationship("Localizador")
    fabricante = db.relationship("Fabricante")

    @property
    def abaixo_minimo(self):
        return self.saldo_minimo and self.saldo <= self.saldo_minimo

    @property
    def opcionais_ativos(self):
        m = [("tag", self.opc_tag), ("ca", self.opc_ca), ("validade", self.opc_validade),
             ("validade_calib", self.opc_validade_calib), ("lote", self.opc_lote)]
        return [k for k, v in m if v]

    # --- Estoque por localizador (fonte da verdade) ---
    def linhas_estoque(self):
        from sqlalchemy import inspect as _insp
        return EstoqueLocalizador.query.filter_by(produto_id=self.id).all()

    def recalcular_saldo(self):
        """Recalcula o saldo TOTAL como soma dos saldos por localizador (mantém compatibilidade)."""
        total = sum((l.quantidade or 0) for l in self.linhas_estoque())
        self.saldo = total
        return total

    def estoque_em(self, localizador_id):
        return EstoqueLocalizador.query.filter_by(produto_id=self.id, localizador_id=localizador_id).first()

    def ajustar_estoque(self, localizador_id, delta):
        """Soma/subtrai 'delta' no localizador informado e atualiza o saldo total. Não deixa negativo."""
        linha = self.estoque_em(localizador_id)
        if linha is None:
            linha = EstoqueLocalizador(produto_id=self.id, localizador_id=localizador_id, quantidade=0)
            db.session.add(linha); db.session.flush()
        linha.quantidade = (linha.quantidade or 0) + delta
        if linha.quantidade < 0:
            linha.quantidade = 0
        self.recalcular_saldo()
        return linha

    @property
    def local_nome(self):
        if self.localizador:
            return self.localizador.codigo
        return self.local.nome if self.local else "—"


class Fabricante(db.Model):
    """Fabricante do item (usado na entrada). Diferente de Fornecedor/vendedor."""
    __tablename__ = "almox_fabricantes"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class NotaFiscalAlmox(db.Model):
    """Nota fiscal usada na entrada (rastreabilidade). Pode ser pré-informada (lançada antes) ou
    informada na entrada (manual). Classificação OPEX/CAPEX é feita pelo admin no desktop."""
    __tablename__ = "almox_notas_fiscais"
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(40))
    fornecedor_nome = db.Column(db.String(160))       # vendedor
    valor = db.Column(db.Float)
    data_emissao = db.Column(db.Date)
    ordem_compra = db.Column(db.String(40))
    itens_json = db.Column(db.Text)                   # itens lidos do XML/PDF (JSON)
    classificacao = db.Column(db.String(10))          # opex | capex | None (a classificar)
    origem = db.Column(db.String(10), default="pre")  # pre | manual | entrada | importada
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def rotulo(self):
        n = self.numero or "s/nº"
        f = self.fornecedor_nome or "—"
        return f"NF {n} · {f}"


class NotificacaoAlmox(db.Model):
    """Notificação para o sininho do admin (ex.: classificar OPEX/CAPEX; NF sem cadastro prévio)."""
    __tablename__ = "almox_notificacoes"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(30))                   # classificar_nf | nf_sem_cadastro | item_pendente
    titulo = db.Column(db.String(160))
    texto = db.Column(db.Text)
    ref_id = db.Column(db.Integer)                    # id da NF / item relacionado
    lida = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class EstoqueLocalizador(db.Model):
    """Saldo do item EM CADA localizador (fonte da verdade do estoque físico).
    O saldo total do item é a SOMA das linhas aqui."""
    __tablename__ = "almox_estoque_localizador"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"), nullable=False)
    localizador_id = db.Column(db.ForeignKey("almox_localizadores.id"))  # None = não atribuído
    quantidade = db.Column(db.Float, default=0)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    produto = db.relationship("ProdutoAlmox")
    localizador = db.relationship("Localizador")
    __table_args__ = (db.UniqueConstraint("produto_id", "localizador_id", name="uq_estoque_loc"),)

    @property
    def local_cod(self):
        return self.localizador.codigo if self.localizador else "não atribuído"


class InstanciaItem(db.Model):
    """Instância (unidade ou grupo de unidades iguais) de um item, com dados próprios:
    TAG, CA, validade, validade de calibração, lote. Usada no Ajuste de instâncias."""
    __tablename__ = "almox_instancias_item"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"), nullable=False)
    localizador_id = db.Column(db.ForeignKey("almox_localizadores.id"))
    tag = db.Column(db.String(60))
    ca = db.Column(db.String(40))
    validade = db.Column(db.Date)
    validade_calib = db.Column(db.Date)
    lote = db.Column(db.String(60))
    quantidade = db.Column(db.Float, default=1)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    produto = db.relationship("ProdutoAlmox")
    localizador = db.relationship("Localizador")


class AjusteInventario(db.Model):
    """Registro de ajuste feito no inventário. Baixas (redução) ficam PENDENTES de aprovação do admin.
    Guarda histórico para consulta de PERDAS por período."""
    __tablename__ = "almox_ajustes_inventario"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"))
    produto_nome = db.Column(db.String(160))
    localizador_cod = db.Column(db.String(40))
    localizador_id = db.Column(db.ForeignKey("almox_localizadores.id"))
    saldo_antes = db.Column(db.Float)
    saldo_novo = db.Column(db.Float)
    diferenca = db.Column(db.Float)                   # negativo = baixa; positivo = acréscimo
    tipo = db.Column(db.String(10))                   # baixa | acrescimo
    status = db.Column(db.String(10), default="aplicado")  # aplicado | pendente | reprovado
    operador_id = db.Column(db.ForeignKey("usuarios.id"))
    operador_nome = db.Column(db.String(160))
    decidido_por = db.Column(db.String(160))
    decidido_em = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


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
# Tarefas dos Perfis de acesso. Cada item: (chave, rótulo, grupo, futura?)
# 'futura=True' aparece desabilitada ("em breve") até a funcionalidade existir.
TAREFAS_PERFIL = [
    # Acesso e permissões (controlam o que a pessoa pode acessar no sistema)
    ("perm_total", "Poder total (acesso a tudo)", "Acesso e permissões", False),
    ("perm_modulo_almox", "Entrar no módulo de almoxarifado", "Acesso e permissões", False),
    ("perm_chaves", "Acessar / gerenciar chaves", "Acesso e permissões", False),
    ("perm_extintores", "Acessar / gerenciar extintores", "Acesso e permissões", False),
    ("perm_colaboradores", "Ver / cadastrar / editar colaboradores", "Acesso e permissões", False),
    ("perm_perfis", "Gerenciar perfis de acesso", "Acesso e permissões", False),
    ("perm_aprovar", "Aprovar / reprovar solicitações", "Acesso e permissões", False),
    ("perm_cotacao", "Enviar cotações", "Acesso e permissões", False),
    ("perm_solicitar", "Criar solicitações", "Acesso e permissões", False),
    ("perm_cadastros", "Acessar cadastros (empresas, tipos, etc.)", "Acesso e permissões", False),
    ("perm_relatorios", "Ver relatórios / central", "Acesso e permissões", False),
    ("perm_log", "Ver log do sistema", "Acesso e permissões", False),
    ("perm_backup", "Baixar backup do banco", "Acesso e permissões", False),
    # Operação / Solicitações
    ("solicitar_criar", "Criar solicitação", "Operação / Solicitações", False),
    ("solicitar_ver_minhas", "Ver minhas solicitações", "Operação / Solicitações", False),
    ("solicitar_ver_todas", "Ver todas as solicitações", "Operação / Solicitações", False),
    ("solicitar_aprovar", "Aprovar / reprovar solicitações", "Operação / Solicitações", False),
    ("cotacao_enviar", "Enviar cotação", "Operação / Solicitações", False),
    ("solicitar_status", "Alterar status de solicitação", "Operação / Solicitações", False),
    ("carga_receber", "Relatório de Carga (recebimento)", "Operação / Solicitações", False),
    ("carga_enviar", "Relatório de Carga (envio)", "Operação / Solicitações", False),
    # Chaves
    ("chave_ver", "Ver chaves", "Chaves", False),
    ("chave_cadastrar", "Cadastrar chave", "Chaves", False),
    ("chave_editar", "Editar chave", "Chaves", False),
    ("chave_historico", "Ver histórico da chave", "Chaves", False),
    ("quadro_cadastrar", "Cadastrar quadro de chaves", "Chaves", False),
    ("chave_qr", "Imprimir QR de chaves / quadro", "Chaves", False),
    ("chave_retirar_devolver", "Retirar / devolver chave (coletor)", "Chaves", False),
    # Extintores
    ("ext_ver", "Ver extintores", "Extintores", False),
    ("ext_inspecionar", "Inspecionar extintor", "Extintores", False),
    ("ext_repor", "Reposição / troca de extintor", "Extintores", False),
    ("ext_conferir", "Conferência no almoxarifado (retorno)", "Extintores", False),
    ("ext_cadastrar", "Cadastrar extintor", "Extintores", False),
    ("ext_desativar", "Desativar extintor", "Extintores", False),
    ("ext_pendencia_etiqueta", "Baixar pendência de etiqueta", "Extintores", False),
    ("ext_qr", "Imprimir QR de extintores", "Extintores", False),
    # Material (estoque)
    ("mat_ver", "Ver material / estoque", "Material (estoque)", False),
    ("mat_cadastrar", "Cadastrar material", "Material (estoque)", False),
    ("mat_entrada", "Entrada de material", "Material (estoque)", False),
    ("mat_saida", "Saída de material", "Material (estoque)", False),
    ("mat_ajuste", "Ajuste de saldo", "Material (estoque)", False),
    ("mat_mover", "Movimentar entre localizadores", "Material (estoque)", False),
    ("mat_inventario", "Inventário", "Material (estoque)", False),
    ("mat_movimentacoes", "Ver movimentações", "Material (estoque)", False),
    ("mat_negativo", "Resolver estoque negativo", "Material (estoque)", False),
    ("mat_qr", "Imprimir QR de material", "Material (estoque)", False),
    ("mat_devolucao_forcada", "Devolução forçada", "Material (estoque)", True),
    ("mat_kit", "Kit (agrupar itens)", "Material (estoque)", True),
    ("mat_unidades", "Unidades / validade / calibração", "Material (estoque)", True),
    # Locais físicos
    ("loc_planta", "Cadastrar Planta", "Locais físicos", True),
    ("loc_armazem", "Cadastrar Armazém", "Locais físicos", True),
    ("loc_localizador", "Cadastrar Localizador", "Locais físicos", True),
    ("loc_gerar", "Gerar localizadores em massa", "Locais físicos", True),
    # Coletor
    ("col_chaves", "Usar coletor — chaves", "Coletor", False),
    ("col_material", "Usar coletor — material", "Coletor", False),
    ("col_movimentacao", "Movimentação (coletor)", "Coletor", False),
    ("col_inventario", "Inventário (coletor)", "Coletor", False),
    ("col_offline", "Coletor offline", "Coletor", True),
    ("col_ajustes", "Ajustes / SISTEMA do coletor", "Coletor", True),
    # Pessoas / Colaboradores
    ("pes_ver", "Ver colaboradores", "Pessoas / Colaboradores", False),
    ("pes_cadastrar", "Cadastrar colaborador", "Pessoas / Colaboradores", False),
    ("pes_editar", "Editar colaborador (cargo / empresa)", "Pessoas / Colaboradores", False),
    ("pes_papel", "Alterar perfil de acesso do colaborador", "Pessoas / Colaboradores", False),
    ("pes_reset_senha", "Resetar senha de colaborador", "Pessoas / Colaboradores", False),
    ("pes_qr", "Imprimir QR de colaborador", "Pessoas / Colaboradores", False),
    ("pes_perfis", "Cadastrar / editar perfis de acesso", "Pessoas / Colaboradores", False),
    # Cadastros (compras)
    ("cad_emp_forn", "Empresas e Fornecedores", "Cadastros", False),
    ("cad_tipos", "Tipos de material", "Cadastros", False),
    ("cad_cidades", "Cidades", "Cadastros", False),
    ("cad_transportadoras", "Transportadoras", "Cadastros", False),
    ("cad_atividades", "Atividades", "Cadastros", False),
    # Relatório
    ("rel_chaves", "Relatório de chaves", "Relatório", False),
    ("rel_material", "Relatórios de material", "Relatório", False),
    ("rel_exportar", "Exportar PDF / CSV", "Relatório", False),
    ("rel_qr_massa", "Impressão de QR em massa", "Relatório", False),
    ("rel_etiquetas", "Central de etiquetas", "Relatório", True),
    # Ajuda / Administração
    ("adm_log", "Ver log do sistema", "Ajuda / Administração", False),
    ("adm_faq", "FAQ", "Ajuda / Administração", False),
    ("adm_sugestao", "Sugestão de melhoria", "Ajuda / Administração", False),
    ("adm_usuarios_antigo", "Gerenciar Usuários - Antigo (Master)", "Ajuda / Administração", False),
    ("adm_backup", "Backup do banco", "Ajuda / Administração", True),
]

# Compatibilidade: as 4 tarefas antigas continuam válidas (perfis já salvos não quebram)
TAREFAS_COLABORADOR = [
    ("inspecionar_extintor", "Inspecionar extintor"),
    ("retirar_repor_extintor", "Retirar / repor extintor"),
    ("pedir_devolver_chave", "Pedir / devolver chave"),
    ("pegar_devolver_material", "Pegar / devolver material"),
]
TAREFAS_DICT = dict(TAREFAS_COLABORADOR)
TAREFAS_DICT.update({k: r for k, r, _g, _f in TAREFAS_PERFIL})

# Grupos na ordem de exibição
TAREFAS_GRUPOS = []
for _k, _r, _g, _f in TAREFAS_PERFIL:
    if _g not in TAREFAS_GRUPOS:
        TAREFAS_GRUPOS.append(_g)


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
    tarefas = db.Column(db.Text, default="")   # chaves separadas por vírgula
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def lista_tarefas(self):
        return [t for t in (self.tarefas or "").split(",") if t]

    @property
    def tarefas_rotulos(self):
        return [TAREFAS_DICT.get(t, t) for t in self.lista_tarefas]


_GRUPO_CHAVES = {"perm_chaves", "chave_ver", "chave_cadastrar", "chave_editar", "chave_historico",
                 "quadro_cadastrar", "chave_qr", "chave_retirar_devolver"}
_GRUPO_EXT = {"perm_extintores", "ext_ver", "ext_inspecionar", "ext_repor", "ext_conferir",
              "ext_cadastrar", "ext_desativar", "ext_pendencia_etiqueta", "ext_qr"}
_GRUPO_MAT = {"mat_ver", "mat_cadastrar", "mat_entrada", "mat_saida", "mat_ajuste", "mat_mover",
              "mat_inventario", "mat_movimentacoes", "mat_negativo", "mat_qr",
              "mat_devolucao_forcada", "mat_kit", "mat_unidades"}
_GRUPO_LOC = {"perm_cadastros", "loc_planta", "loc_armazem", "loc_localizador", "loc_gerar"}
_GRUPO_ALMOX = _GRUPO_CHAVES | _GRUPO_EXT | _GRUPO_MAT | _GRUPO_LOC | {"perm_modulo_almox"}


def perm_from_tasks(perms, prop):
    """Fonte ÚNICA de verdade: dado o conjunto de tarefas de um perfil, diz se a propriedade vale.
    Honra tanto as chaves 'grossas' (perm_*) quanto as granulares (chave_*, ext_*, mat_*, loc_*)."""
    perms = perms or set()
    if prop == "is_admin":
        return "perm_total" in perms
    if "perm_total" in perms:
        return True
    if prop == "pode_almox_modulo":
        return bool(perms & _GRUPO_ALMOX)
    if prop == "is_almox":
        return ("perm_modulo_almox" in perms) or bool(perms & _GRUPO_MAT)
    if prop == "pode_chaves":
        return bool(perms & _GRUPO_CHAVES)
    if prop == "pode_extintores":
        return bool(perms & _GRUPO_EXT)
    if prop == "pode_material":
        return bool(perms & _GRUPO_MAT)
    if prop == "pode_colaboradores":
        return "perm_colaboradores" in perms
    if prop == "pode_solicitar":
        return bool(perms & {"perm_solicitar", "solicitar_criar", "solicitar_ver_minhas"})
    return prop in perms


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

    # ---- Permissões: derivadas do PERFIL DE ACESSO (PapelColaborador) ----
    # self.papel guarda o NOME do perfil cadastrado. As permissões vêm das
    # tarefas marcadas nesse perfil. Se não houver perfil correspondente
    # (colaborador ainda não migrado), cai no comportamento ANTIGO (anti-lockout).
    @property
    def _p(self): return (self.papel or "").strip().lower()

    def _perms_efetivas(self):
        cache = getattr(self, "_perm_cache", None)
        if cache is not None:
            return cache
        perfil = None
        nome = (self.papel or "").strip()
        if nome:
            perfil = PapelColaborador.query.filter(
                db.func.upper(PapelColaborador.nome) == nome.upper()).first()
        if perfil is not None:
            perms = set(perfil.lista_tarefas)          # fonte única: tarefas do perfil
        else:
            # Fallback anti-lockout: reproduz o acesso antigo enquanto não migrar.
            p = self._p
            perms = {"perm_solicitar"}                 # antes: pode_solicitar era sempre True
            if p == "admin":
                perms.add("perm_total")
            if p in ("admin", "almoxarifado"):
                perms |= {"perm_modulo_almox", "perm_chaves",
                          "perm_extintores", "perm_colaboradores"}
        self._perm_cache = perms
        return perms

    def _tem(self, chave):
        p = self._perms_efetivas()
        return ("perm_total" in p) or (chave in p)

    @property
    def is_admin(self): return "perm_total" in self._perms_efetivas()
    @property
    def is_master(self): return False
    @property
    def is_almox(self): return perm_from_tasks(self._perms_efetivas(), "is_almox")
    @property
    def pode_solicitar(self): return perm_from_tasks(self._perms_efetivas(), "pode_solicitar")
    @property
    def senha_temporaria(self): return False
    @property
    def pode_almox_modulo(self): return perm_from_tasks(self._perms_efetivas(), "pode_almox_modulo")
    @property
    def pode_chaves(self): return perm_from_tasks(self._perms_efetivas(), "pode_chaves")
    @property
    def pode_extintores(self): return perm_from_tasks(self._perms_efetivas(), "pode_extintores")
    @property
    def pode_material(self): return perm_from_tasks(self._perms_efetivas(), "pode_material")
    @property
    def pode_colaboradores(self): return perm_from_tasks(self._perms_efetivas(), "pode_colaboradores")
    @property
    def is_viewer(self):
        # só leitura = nenhuma permissão de acesso/escrita
        return not (self.is_admin or self.pode_almox_modulo or self.pode_solicitar
                    or self.pode_chaves or self.pode_extintores or self.pode_colaboradores)
    def pode_gerir(self, alvo): return self.is_admin


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
    """Log de ações do sistema (chaves, extintores, material, colaboradores, compras...)."""
    __tablename__ = "almox_log"
    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.ForeignKey("usuarios.id"))
    autor_nome = db.Column(db.String(160))       # nome do ator (usuário OU colaborador)
    categoria = db.Column(db.String(30))
    detalhe = db.Column(db.String(400))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    autor = db.relationship("Usuario")


# --- Preenche automaticamente a coluna legada 'nome' do Fornecedor ---
# Garante que nome nunca fique NULL (a coluna é NOT NULL no banco antigo),
# mantendo-a sincronizada com nome_fantasia/razao_social. Vale em qualquer
# ponto que crie/edite um Fornecedor, nos dois bancos (SQLite e Postgres).
def _forn_preenche_nome(mapper, connection, target):
    target.nome = (target.nome_fantasia or target.razao_social
                   or target.email or target.nome or "SEM NOME")
    # coluna legada 'email' também é NOT NULL no banco antigo — nunca deixar NULL
    if target.email is None:
        target.email = ""


event.listen(Fornecedor, "before_insert", _forn_preenche_nome)
event.listen(Fornecedor, "before_update", _forn_preenche_nome)
