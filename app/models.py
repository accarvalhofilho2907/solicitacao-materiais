from datetime import datetime, date

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
    pode_alternar_planta = db.Column(db.Boolean, default=False)   # [134] Admin: concedido pelo Admin Master
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

    @property
    def plantas(self):
        """[134] Plantas às quais este usuário está vinculado."""
        return [up.planta for up in UsuarioPlanta.query.filter_by(usuario_id=self.id).all()]

    @property
    def pode_ver_outras_plantas(self):
        """[134] Master sempre pode. Admin só se o Master liberou (pode_alternar_planta)."""
        return bool(self.is_master or (self.is_admin and self.pode_alternar_planta))

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
    def pode_locais(self):
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_relatorios(self):
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_coletor(self):
        return self.papel in ("admin", "almoxarifado")
    @property
    def pode_criar_solicitacao(self):
        return self.papel in ("admin", "almoxarifado", "solicitante")
    @property
    def pode_ver_solicitacoes(self):
        return self.papel in ("admin", "almoxarifado", "solicitante")
    def tem_tarefa(self, tarefa):
        # staff do módulo (admin/almoxarifado) pode todas as tarefas do módulo
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
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [134] dono do registro
    solicitante_id = db.Column(db.ForeignKey("usuarios.id"), nullable=True)
    solicitante_colab_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    solicitante_nome = db.Column(db.String(160))   # snapshot do autor (usuário OU colaborador)
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
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    quantidade_alterada_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    quantidade_alterada_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    quantidade_alterada_em = db.Column(db.DateTime)
    quantidade_recebida = db.Column(db.Integer, default=0)   # chegada parcial acumulada

    prazo_cotacao = db.Column(db.Date)   # data-limite p/ retorno da cotação (item 93)
    fornecedor_definido_id = db.Column(db.ForeignKey("fornecedores.id"))
    frete_tipo = db.Column(db.String(10))
    frete_modalidade = db.Column(db.String(20))
    transportadora_id = db.Column(db.ForeignKey("transportadoras.id"))
    cidade_retirada_id = db.Column(db.ForeignKey("cidades.id"))
    prazo_recebimento = db.Column(db.Date)
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    chegada_confirmada_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    chegada_confirmada_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    chegada_em = db.Column(db.DateTime)

    tipo = db.relationship("TipoMaterial")
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
    def solicitante_display(self):
        if self.solicitante_nome:
            return self.solicitante_nome
        if self.solicitante_colab_id:
            cb = db.session.get(Colaborador, self.solicitante_colab_id)
            if cb:
                return cb.nome
        if self.solicitante_id and self.solicitante:
            return self.solicitante.nome
        return "—"

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

    @property
    def editor_qtd(self):
        """[fix 23/09] Quem alterou a quantidade — Usuario OU Colaborador, o que existir."""
        if self.quantidade_alterada_por_usuario_id:
            return db.session.get(Usuario, self.quantidade_alterada_por_usuario_id)
        if self.quantidade_alterada_por_colaborador_id:
            return db.session.get(Colaborador, self.quantidade_alterada_por_colaborador_id)
        return None

    @property
    def confirmador_chegada(self):
        """[fix 23/09] Quem confirmou a chegada — Usuario OU Colaborador, o que existir."""
        if self.chegada_confirmada_por_usuario_id:
            return db.session.get(Usuario, self.chegada_confirmada_por_usuario_id)
        if self.chegada_confirmada_por_colaborador_id:
            return db.session.get(Colaborador, self.chegada_confirmada_por_colaborador_id)
        return None


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
    # [fix CRÍTICO 23/09] autor_id era FK ÚNICA pra usuarios.id, NULLABLE=FALSE — quebrava com
    # ForeignKeyViolation sempre que quem comenta é um Colaborador (ex.: com permissão de
    # is_admin via tarefa perm_total, ou pode_solicitar). Separado em duas colunas, nenhuma
    # delas NOT NULL (senão travaria de novo pro caso oposto).
    autor_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    autor_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    texto = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    autor = db.relationship("Usuario")

    @property
    def autor_nome(self):
        if self.autor_usuario_id:
            u = db.session.get(Usuario, self.autor_usuario_id)
            return u.nome if u else "—"
        if self.autor_colaborador_id:
            c = db.session.get(Colaborador, self.autor_colaborador_id)
            return c.nome if c else "—"
        return "—"

    @property
    def autor_eh_admin(self):
        """[fix 23/09] Substitui o antigo `c.autor.is_admin` do template — o autor agora pode
        ser Usuario OU Colaborador, cada um com sua própria noção de is_admin."""
        if self.autor_usuario_id:
            u = db.session.get(Usuario, self.autor_usuario_id)
            return bool(u and u.is_admin)
        if self.autor_colaborador_id:
            c = db.session.get(Colaborador, self.autor_colaborador_id)
            return bool(c and c.is_admin)
        return False


class PedidoCompra(db.Model):
    __tablename__ = "pedidos_compra"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    enviado_em = db.Column(db.DateTime, default=datetime.utcnow)
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    enviado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    enviado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
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
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    registrado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    registrado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    recebido_em = db.Column(db.DateTime, default=datetime.utcnow)
    fornecedor = db.relationship("Fornecedor")


class Notinha(db.Model):
    __tablename__ = "notinhas"
    id = db.Column(db.Integer, primary_key=True)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [134] dono do registro
    data = db.Column(db.Date, nullable=False)
    competencia = db.Column(db.String(7))   # "AAAA-MM" (mês de referência)
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"), nullable=False)
    atividade_id = db.Column(db.ForeignKey("atividades.id"))
    valor = db.Column(db.Numeric(12, 2), nullable=False)
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    fornecedor = db.relationship("Fornecedor")
    atividade = db.relationship("Atividade")


class LogSolicitacao(db.Model):
    __tablename__ = "logs_solicitacao"
    id = db.Column(db.Integer, primary_key=True)
    solicitacao_id = db.Column(db.ForeignKey("solicitacoes.id"), nullable=False)
    evento = db.Column(db.String(300), nullable=False)
    autor_id = db.Column(db.ForeignKey("usuarios.id"))
    autor_nome = db.Column(db.String(160))   # snapshot (usuário OU colaborador)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    autor = db.relationship("Usuario")

    @property
    def autor_display(self):
        return self.autor_nome or (self.autor.nome if self.autor_id and self.autor else "—")


class Sugestao(db.Model):
    __tablename__ = "sugestoes"
    id = db.Column(db.Integer, primary_key=True)
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    autor_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    autor_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    texto = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    autor = db.relationship("Usuario")

    @property
    def autor_nome(self):
        if self.autor_usuario_id:
            u = db.session.get(Usuario, self.autor_usuario_id)
            return u.nome if u else "—"
        if self.autor_colaborador_id:
            c = db.session.get(Colaborador, self.autor_colaborador_id)
            return c.nome if c else "—"
        return "Anônimo"


# ==================== MÓDULO ALMOXARIFADO (item novo) ====================
# Tabelas de apoio ao módulo Chaves / Extintores / Colaboradores.
# Criadas por db.create_all(); colunas novas entram pelo _light_migrate().

class QuadroChave(db.Model):
    """Localizador das chaves (item roadmap §4). Lista própria e pesquisável."""
    __tablename__ = "almox_quadros_chave"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), unique=True, nullable=False)
    qr_uid = db.Column(db.String(20), unique=True)   # QR próprio do quadro (QUAD-...)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [correção] dono do registro
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    planta = db.relationship("Planta")


class Chave(db.Model):
    __tablename__ = "almox_chaves"
    id = db.Column(db.Integer, primary_key=True)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [134] dono do registro
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
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [134] dono do registro
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


class UsuarioPlanta(db.Model):
    """[134] Vinculo N-N: um Usuario pode pertencer a mais de uma Planta ao mesmo tempo."""
    __tablename__ = "usuarios_plantas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.ForeignKey("usuarios.id"), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("usuario_id", "planta_id", name="uq_usuario_planta"),)

    planta = db.relationship("Planta")


class ColaboradorPlanta(db.Model):
    """[134] Vinculo N-N: um Colaborador pode pertencer a mais de uma Planta ao mesmo tempo."""
    __tablename__ = "colaboradores_plantas"
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("colaborador_id", "planta_id", name="uq_colaborador_planta"),)

    planta = db.relationship("Planta")


class Predio(db.Model):
    """[v3] "Edificação" (rótulo visível ao usuário — renomeado de "Prédio" em 19/09) dentro
    de uma planta (ex.: "D6", "Subestação Central") — cadastro novo, pedido para uso em
    Programação de Atividades. Distinto de Armazem (que é sobre estoque/localização de
    material). O nome técnico da classe/tabela/coluna continua "Predio" por compatibilidade
    (evita quebrar FK e migração) — só o texto exibido na tela mudou para "Edificação"."""
    __tablename__ = "sf_predios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    planta = db.relationship("Planta")


class EquipamentoTerceiro(db.Model):
    """[22/09] Cadastro geral de Terceiro — Equipamentos (diferente de MaquinarioPesadoTerceiro,
    que tem o fluxo de horímetro). Cadastro básico: nome, planta, empresa/fornecedor."""
    __tablename__ = "sf_equipamentos_terceiro"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    planta = db.relationship("Planta")
    fornecedor = db.relationship("Fornecedor")


class MaquinarioPesadoTerceiro(db.Model):
    """[22/09] Cadastro de máquina pesada de terceiro (ex.: escavadeira, trator) — vinculada a
    uma AtividadeGrupo com horimetro=True. Planta é fixa no cadastro; a EMPRESA que opera a
    máquina pode variar por relatório (RegistroHorimetro.fornecedor_id), por isso o fornecedor
    aqui é só um "padrão" sugerido, não obrigatório por relatório."""
    __tablename__ = "sf_maquinario_pesado_terceiro"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    fornecedor_padrao_id = db.Column(db.ForeignKey("fornecedores.id"))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    planta = db.relationship("Planta")
    fornecedor_padrao = db.relationship("Fornecedor")


class RegistroHorimetro(db.Model):
    """[22/09] Um lançamento de horímetro (início OU fim do dia) de uma AtividadeDia cuja
    atividade tem horimetro=True. Cada AtividadeDia de uma atividade com horímetro tem, no
    máximo, 2 registros: tipo=INICIO (feito ao começar o dia) e tipo=FIM (feito ao encerrar,
    junto com o report normal de fotos/descrição da atividade). A empresa (fornecedor) é
    informada em CADA registro — pode variar dia a dia, mesmo sendo a mesma máquina.
    [23/09] status: PENDENTE|APROVADO — mesmo espírito do RDO. Só pode ser excluído enquanto
    PENDENTE (ver painel_horimetros_excluir)."""
    __tablename__ = "sf_registros_horimetro"
    id = db.Column(db.Integer, primary_key=True)
    dia_id = db.Column(db.ForeignKey("sf_atividade_dias.id"), nullable=False)
    maquina_id = db.Column(db.ForeignKey("sf_maquinario_pesado_terceiro.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)   # INICIO | FIM
    valor_horimetro = db.Column(db.Float, nullable=False)
    foto_painel_url = db.Column(db.Text)   # 1 foto só, fora das 4 fotos normais da atividade
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"))   # empresa operando NESTE dia
    status = db.Column(db.String(20), default="PENDENTE")   # [23/09] PENDENTE | APROVADO
    aprovado_em = db.Column(db.DateTime)
    aprovado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    aprovado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    maquina = db.relationship("MaquinarioPesadoTerceiro")
    fornecedor = db.relationship("Fornecedor")
    dia = db.relationship("AtividadeDia", backref="registros_horimetro")


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
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))   # [134] dono do registro
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
ITEM_ETIQUETA_EXTINTOR = "QR Code de inspeção grudado e em bom estado?"


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
    ("chave_desativar", "Desativar / reativar chave", "Chaves", False),
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
    # Facilities (SIGA — motor de checklist/inspeção de equipamentos)
    ("fac_ver", "Ver telas de Facilities (checklist)", "Facilities", False),
    ("fac_inspecionar", "Executar checklist de inspeção sobre um material", "Facilities", False),
    ("fac_gerir_modelos", "Criar/editar modelos de checklist (gestão)", "Facilities", False),
    ("fac_criar_atividade", "Criar atividades programadas (Facilities)", "Facilities", False),
    ("fac_ver_programacao", "Ver a programação/calendário de TODAS as atividades (gestão)", "Facilities", False),
    ("fac_rdo", "Criar/ver Relatório Diário de Obra (RDO)", "Facilities", False),
    ("fac_encarregado_campo", "Encarregado de Campo (aprova/retifica atividades)", "Facilities", False),
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
                 "quadro_cadastrar", "chave_qr", "chave_retirar_devolver", "chave_desativar"}
_GRUPO_EXT = {"perm_extintores", "ext_ver", "ext_inspecionar", "ext_repor", "ext_conferir",
              "ext_cadastrar", "ext_desativar", "ext_pendencia_etiqueta", "ext_qr"}
_GRUPO_MAT = {"mat_ver", "mat_cadastrar", "mat_entrada", "mat_saida", "mat_ajuste", "mat_mover",
              "mat_inventario", "mat_movimentacoes", "mat_negativo", "mat_qr",
              "mat_devolucao_forcada", "mat_kit", "mat_unidades"}
_GRUPO_LOC = {"perm_cadastros", "loc_planta", "loc_armazem", "loc_localizador", "loc_gerar"}
_GRUPO_COLETOR = {"col_chaves", "col_material", "col_movimentacao", "col_inventario"}
_GRUPO_FAC = {"fac_ver", "fac_inspecionar", "fac_gerir_modelos", "fac_criar_atividade",
              "fac_ver_programacao", "fac_rdo", "fac_encarregado_campo"}
_GRUPO_ALMOX = (_GRUPO_CHAVES | _GRUPO_EXT | _GRUPO_MAT | _GRUPO_LOC | _GRUPO_COLETOR
                | {"perm_modulo_almox"})


def perm_from_tasks(perms, prop):
    """Fonte ÚNICA de verdade: dado o conjunto de tarefas de um perfil, diz se a propriedade vale.
    Honra tanto as chaves 'grossas' (perm_*) quanto as granulares (chave_*, ext_*, mat_*, loc_*, col_*)."""
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
    if prop == "pode_locais":
        return ("perm_cadastros" in perms) or bool(perms & _GRUPO_LOC)
    if prop == "pode_relatorios":
        return ("perm_relatorios" in perms) or bool(perms & {"carga_receber", "carga_enviar"})
    if prop == "pode_coletor":
        return bool(perms & _GRUPO_COLETOR)
    if prop == "pode_facilities":
        return bool(perms & _GRUPO_FAC)
    if prop == "pode_facilities_inspecionar":
        return ("fac_inspecionar" in perms)
    if prop == "pode_facilities_cadastrar":
        return ("fac_cadastrar_equipamento" in perms)
    if prop == "pode_facilities_gerir":
        return ("fac_gerir_modelos" in perms)
    if prop == "pode_criar_atividade":
        return ("fac_criar_atividade" in perms)
    if prop == "pode_ver_programacao":
        return ("fac_ver_programacao" in perms) or ("fac_encarregado_campo" in perms)
    if prop == "pode_rdo":
        return ("fac_rdo" in perms) or ("fac_encarregado_campo" in perms)
    if prop == "eh_encarregado_campo":
        return ("fac_encarregado_campo" in perms)
    if prop == "pode_colaboradores":
        return "perm_colaboradores" in perms
    if prop == "pode_criar_solicitacao":
        return bool(perms & {"perm_solicitar", "solicitar_criar"})
    if prop == "pode_ver_solicitacoes":
        return bool(perms & {"perm_solicitar", "solicitar_criar", "solicitar_ver_minhas", "solicitar_ver_todas"})
    if prop == "pode_solicitar":
        return bool(perms & {"perm_solicitar", "solicitar_criar", "solicitar_ver_minhas"})
    return prop in perms


class AusenciaColaborador(db.Model):
    """[item novo] Registro de férias/ausência de um Colaborador — motivo, período (em dias
    úteis, calculado a partir da data de início) e data de retorno. Usado para: (1) avisar
    no Resumo Diário quem está ausente naquele dia; (2) no futuro, pode alimentar a checagem
    de conflito de agenda (ainda não conectado a isso nesta leva)."""
    __tablename__ = "sf_ausencias_colaborador"
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"), nullable=False)
    motivo = db.Column(db.String(200), nullable=False)   # "Férias", "Atestado médico", etc.
    data_inicio = db.Column(db.Date, nullable=False)
    dias_uteis = db.Column(db.Integer, nullable=False)
    data_retorno = db.Column(db.Date, nullable=False)     # calculada (próximo dia útil após o período)
    # [fix 23/09] mesmo padrão de bug corrigido em outros modelos — separado em duas colunas.
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    colaborador = db.relationship("Colaborador", foreign_keys=[colaborador_id])

    def esta_ausente_em(self, data_ref):
        return self.data_inicio <= data_ref < self.data_retorno


class EncarregadoEmpresa(db.Model):
    """[v3] Liga um Colaborador (com papel/tarefa "Encarregado de Campo") às empresas
    (Fornecedor) pelas quais ele é responsável — usado para filtrar quais atividades ele
    vê para aprovar."""
    __tablename__ = "sf_encarregado_empresa"
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"), nullable=False)
    fornecedor_id = db.Column(db.ForeignKey("fornecedores.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("colaborador_id", "fornecedor_id", name="uq_encarregado_empresa"),)

    fornecedor = db.relationship("Fornecedor")


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
    def plantas(self):
        """[134] Plantas às quais este colaborador está vinculado."""
        return [cp.planta for cp in ColaboradorPlanta.query.filter_by(colaborador_id=self.id).all()]
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
    def pode_locais(self): return perm_from_tasks(self._perms_efetivas(), "pode_locais")
    @property
    def pode_relatorios(self): return perm_from_tasks(self._perms_efetivas(), "pode_relatorios")
    @property
    def pode_coletor(self): return perm_from_tasks(self._perms_efetivas(), "pode_coletor")
    @property
    def pode_facilities(self): return perm_from_tasks(self._perms_efetivas(), "pode_facilities")
    @property
    def pode_facilities_inspecionar(self): return perm_from_tasks(self._perms_efetivas(), "pode_facilities_inspecionar")
    @property
    def pode_facilities_cadastrar(self): return perm_from_tasks(self._perms_efetivas(), "pode_facilities_cadastrar")
    @property
    def pode_facilities_gerir(self): return perm_from_tasks(self._perms_efetivas(), "pode_facilities_gerir")
    @property
    def pode_criar_atividade(self): return perm_from_tasks(self._perms_efetivas(), "pode_criar_atividade")
    @property
    def pode_ver_programacao(self): return perm_from_tasks(self._perms_efetivas(), "pode_ver_programacao")
    @property
    def pode_rdo(self): return perm_from_tasks(self._perms_efetivas(), "pode_rdo")
    @property
    def eh_encarregado_campo(self): return perm_from_tasks(self._perms_efetivas(), "eh_encarregado_campo")
    @property
    def empresas_encarregado(self):
        """[v3] Fornecedores pelos quais este Colaborador é Encarregado de Campo."""
        return [e.fornecedor for e in EncarregadoEmpresa.query.filter_by(colaborador_id=self.id).all()]
    @property
    def pode_criar_solicitacao(self): return perm_from_tasks(self._perms_efetivas(), "pode_criar_solicitacao")
    @property
    def pode_ver_solicitacoes(self): return perm_from_tasks(self._perms_efetivas(), "pode_ver_solicitacoes")
    def tem_tarefa(self, tarefa): return perm_from_tasks(self._perms_efetivas(), tarefa)
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


class RoadmapNota(db.Model):
    __tablename__ = "roadmap_nota"
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, default="")
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RoadmapItem(db.Model):
    __tablename__ = "roadmap_item"
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    feito = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ColetaAvulsa(db.Model):
    __tablename__ = "coleta_avulsa"
    id = db.Column(db.Integer, primary_key=True)
    material = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.String(40))
    cidade_nome = db.Column(db.String(160))
    fornecedor_nome = db.Column(db.String(160))
    coletado = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================================
# SIGA / FACILITIES — MOTOR GENÉRICO DE CHECKLIST E INSPEÇÃO
# ============================================================================
# Decisão de arquitetura (registrada com Antonio): em vez de cada tipo de equipamento
# novo (gerador, veículo, ar-condicionado...) ganhar um checklist "hardcoded" no
# código (como o extintor tem hoje, via CHECK_EXTINTOR), o Facilities usa um motor
# GENÉRICO: só o ADMIN cria/edita MODELOS de checklist (nome, itens); qualquer
# EQUIPAMENTO cadastrado aponta para um modelo; a EXECUÇÃO usa esse modelo na hora.
#
# Regra de reprovação de cada item (definida por Antonio), por tipo:
#   - IMPEDITIVO: reprovado -> bloqueia gerar/fechar o checklist até resolver.
#   - ATENCAO: reprovado -> não bloqueia, só fica registrado como pendência.
#   - TEMPORARIO: começa como ATENCAO, mas tem um PRAZO PRÓPRIO em dias (definido
#     item a item, na criação do modelo). Se o MESMO item continuar falho e o
#     prazo vencer por TEMPO CORRIDO (não depende de nova inspeção), o item vira
#     IMPEDITIVO automaticamente — feito por uma rotina periódica que varre
#     ItemFalhaAberta (não pelo ato de inspecionar de novo).
#
# O extintor NÃO migra para este motor por enquanto (decisão em aberto de Antonio);
# este motor nasce para os equipamentos NOVOS de Facilities.

TIPO_ITEM_CHECKLIST = ("IMPEDITIVO", "ATENCAO", "TEMPORARIO")


class ModeloChecklist(db.Model):
    """Um "formulário" de checklist reutilizável (ex.: "Inspeção de Gerador",
    "Ronda de Veículo"). Só o Admin/Master cria e edita. [M2] Escolhido livremente
    na hora de executar — não há vínculo fixo gravado no cadastro de Material.
    [fix 23/09] criado_por separado em duas colunas (mesmo padrão de AtividadeDia.
    aprovado_por) — mesmo sendo raro um Colaborador criar isso, evita o mesmo tipo de
    ForeignKeyViolation."""
    __tablename__ = "sf_modelos_checklist"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    descricao = db.Column(db.String(300))
    ativo = db.Column(db.Boolean, default=True)
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    itens = db.relationship("ItemChecklist", backref="modelo", order_by="ItemChecklist.ordem",
                            cascade="all, delete-orphan")

    @property
    def qtd_itens(self):
        return len(self.itens)


class ItemChecklist(db.Model):
    """Um item dentro de um ModeloChecklist. tipo define a regra de bloqueio;
    prazo_dias só é usado quando tipo == 'TEMPORARIO'."""
    __tablename__ = "sf_itens_checklist"
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.ForeignKey("sf_modelos_checklist.id"), nullable=False)
    texto = db.Column(db.String(300), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="ATENCAO")  # ver TIPO_ITEM_CHECKLIST
    prazo_dias = db.Column(db.Integer)   # obrigatório (na prática) se tipo == TEMPORARIO
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)


class ExecucaoChecklist(db.Model):
    """[M2] Uma inspeção/execução concluída sobre um item de MATERIAL (ProdutoAlmox), usando um
    ModeloChecklist — os dois escolhidos LIVREMENTE no momento da execução (não há vínculo fixo
    gravado no cadastro do material; o próprio modelo de checklist comporta um "cabeçalho" onde a
    pessoa registra dados como marca/modelo/nº de série, guardado em cabecalho_json).
    resultado_geral: 'OK' (nada reprovado), 'ATENCAO' (algo em atenção, mas fechou),
    'IMPEDITIVO' (tinha item impeditivo — nesse caso o registro existe mas a UI deve
    ter bloqueado o fechamento; guardamos para auditoria de tentativa)."""
    __tablename__ = "sf_execucoes_checklist"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"), nullable=False)
    modelo_id = db.Column(db.ForeignKey("sf_modelos_checklist.id"), nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    executado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    executado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    executado_em = db.Column(db.DateTime, default=datetime.utcnow)
    resultado_geral = db.Column(db.String(20))
    respostas_json = db.Column(db.Text)     # snapshot das respostas item a item (JSON)
    cabecalho_json = db.Column(db.Text)     # dados livres digitados na hora (marca, série, etc.)
    observacoes = db.Column(db.Text)
    fotos_json = db.Column(db.Text)         # [v3] fotos do checklist, salvas via storage.salvar_imagem

    produto = db.relationship("ProdutoAlmox")
    modelo = db.relationship("ModeloChecklist")
    planta = db.relationship("Planta")


class ItemFalhaAberta(db.Model):
    """[M2] O "relógio" de um item TEMPORARIO reprovado e ainda não corrigido, agora ligado ao
    MATERIAL (produto_id) inspecionado, não mais a um Equipamento. Criado quando uma execução
    reprova um item TEMPORARIO; resolvido quando uma execução seguinte aprova o mesmo item NO
    MESMO PRODUTO. Uma rotina periódica varre os registros com status='ATENCAO' cujo prazo_final
    já passou e promove para status='IMPEDITIVO' — SEM depender de nova inspeção acontecer (é por
    tempo corrido, conforme definido por Antonio)."""
    __tablename__ = "sf_falhas_abertas"
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"), nullable=False)
    item_checklist_id = db.Column(db.ForeignKey("sf_itens_checklist.id"), nullable=False)
    aberto_em = db.Column(db.DateTime, default=datetime.utcnow)
    prazo_final = db.Column(db.Date)   # aberto_em + prazo_dias do item
    status = db.Column(db.String(20), default="ATENCAO")   # ATENCAO -> IMPEDITIVO (promovido) -> RESOLVIDO
    promovido_em = db.Column(db.DateTime)
    resolvido_em = db.Column(db.DateTime)

    produto = db.relationship("ProdutoAlmox")
    item_checklist = db.relationship("ItemChecklist")

    @property
    def dias_em_aberto(self):
        fim = self.resolvido_em.date() if self.resolvido_em else date.today()
        return (fim - self.aberto_em.date()).days


# ============================================================================
# SIGA / FACILITIES — PROGRAMAÇÃO E RELATÓRIO DE ATIVIDADES ("Rotina")
# ============================================================================
# Decisão (Antonio): agenda SIMPLES por enquanto, sem recorrência automática (fica para
# uma etapa futura). Programação = o que deve acontecer, quando, quem é responsável.
# Relatório de Atividades = o que de fato aconteceu (pode ou não estar ligado a uma
# atividade programada), no mesmo espírito do Relatório de Carga já existente.

# ============================================================================
# PROGRAMAÇÃO DE ATIVIDADES v3 — grupo (planejamento) + dias (execução dia a dia)
# ============================================================================
# Decisão (Antonio, especificação v3): a atividade "mãe" (AtividadeGrupo) carrega o
# planejamento (título, duração em dias ÚTEIS, recorrência, colaboradores, fotos de
# "antes"). Ao salvar, o sistema gera N AtividadeDia (uma por dia útil, pulando fins de
# semana e feriados) — cada uma com sua PRÓPRIA % de conclusão, fotos e status de
# aprovação. Isso separa "o que foi planejado" de "o que aconteceu em cada dia".
#
# Duração em dias úteis: 1 semana = 5, 1 mês ≈ 22, 1 ano ≈ 260 (conversão fixa, não
# civil). Recorrência: intervalo fixo em dias corridos (7/14/30/60/90/180/365/730),
# restrito a valores >= duração da atividade em dias úteis (trava de bom senso, não
# múltiplo matemático exato).
#
# % de conclusão: UMA por AtividadeDia (não por colaborador) — qualquer colaborador da
# atividade pode preencher, mas o sistema registra HISTÓRICO de quem preencheu cada vez
# (RegistroPreenchimento). Se a % cai em relação ao dia anterior da mesma atividade,
# exige justificativa. Fluxo de aprovação do Encarregado: só Aprovar ou Retificar (sem
# reprovar — retificar já sai aprovado).

UNIDADES_DURACAO_DIAS_UTEIS = {"dias": None, "semana": 5, "mes": 22, "ano": 260}
OPCOES_RECORRENCIA = [
    (7, "Semanal (a cada 7 dias)"), (14, "Quinzenal (a cada 14 dias)"),
    (30, "Mensal (a cada 30 dias)"), (60, "Bimestral (a cada 60 dias)"),
    (90, "Trimestral (a cada 90 dias)"), (180, "Semestral (a cada 180 dias)"),
    (365, "Anual (a cada 365 dias)"), (730, "Bianual (a cada 730 dias)"),
]


class Feriado(db.Model):
    """Cadastro simples de feriados (nacionais por padrão) — usado para pular esses dias
    ao gerar as linhas (AtividadeDia) de uma atividade, junto com sábados/domingos."""
    __tablename__ = "sf_feriados"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True)
    nome = db.Column(db.String(160), nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class AtividadeGrupo(db.Model):
    """A atividade "mãe": o planejamento. Ao salvar, gera N AtividadeDia (dias úteis).
    [19/09] tipo: NORMAL usa o report de "dias restantes" (ver AtividadeDia.dias_restantes).
    [23/09 CORREÇÃO DE CONCEITO] FIXA não é "duração fixa em dias" — é uma atividade CONTÍNUA,
    SEM FIM DEFINIDO (ex.: ronda diária, monitoramento contínuo). Não tem duracao_dias_uteis
    significativa; os dias são gerados SOB DEMANDA (ver _garantir_dias_fixa_ate()) sempre que
    alguém abre uma tela numa data futura, até a atividade ser ENCERRADA explicitamente
    (encerrada=True), que é quando a geração automática para."""
    __tablename__ = "sf_atividades_grupo"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    tipo = db.Column(db.String(10), default="NORMAL")   # NORMAL | FIXA
    data_inicio = db.Column(db.Date, nullable=False)
    unidade_duracao = db.Column(db.String(10), default="dias")   # dias|semana|mes|ano
    duracao_dias_uteis = db.Column(db.Integer)   # [23/09] nullable — FIXA não usa este campo
    recorrencia_dias = db.Column(db.Integer)   # null = não recorrente
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"))
    predio_id = db.Column(db.ForeignKey("sf_predios.id"))   # [v3] Prédio (cadastro novo)
    produto_id = db.Column(db.ForeignKey("almox_produtos.id"))
    fotos_antes_json = db.Column(db.Text)   # até 4 caminhos de arquivo
    status_cadastro = db.Column(db.String(20), default="COMPLETO")  # COMPLETO|INCOMPLETO
    motivo_cancelamento = db.Column(db.Text)
    maquina_horimetro_id = db.Column(db.ForeignKey("sf_maquinario_pesado_terceiro.id"))  # [22/09] se preenchido, ativa o fluxo de 2 reports/dia com horímetro
    encerrada = db.Column(db.Boolean, default=False)   # [23/09] só relevante pra FIXA — para a geração automática de novos dias
    encerrada_em = db.Column(db.DateTime)
    # [fix CRÍTICO 23/09] criado_por era uma FK ÚNICA pra usuarios.id — quebrava sempre que
    # quem cria a atividade é um Colaborador (Encarregado logado normalmente, não via QR),
    # cujo ID não existe na tabela de usuários. Mesmo padrão de bug já corrigido em
    # AtividadeDia.aprovado_por — separado em duas colunas.
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    planta = db.relationship("Planta")
    predio = db.relationship("Predio")
    produto = db.relationship("ProdutoAlmox")
    maquina_horimetro = db.relationship("MaquinarioPesadoTerceiro")
    dias = db.relationship("AtividadeDia", backref="grupo", order_by="AtividadeDia.data",
                           cascade="all, delete-orphan")
    colaboradores = db.relationship("AtividadeColaborador", backref="grupo",
                                    cascade="all, delete-orphan")

    @property
    def responsavel(self):
        r = next((c for c in self.colaboradores if c.eh_responsavel), None)
        return r.colaborador if r else None

    @property
    def tem_horimetro(self):
        return self.maquina_horimetro_id is not None

    @property
    def eh_fixa(self):
        return self.tipo == "FIXA"


class AtividadeColaborador(db.Model):
    """Um colaborador participante de uma AtividadeGrupo. O PRIMEIRO adicionado é marcado
    eh_responsavel=True (o titular); os demais são colaboradores normais da atividade."""
    __tablename__ = "sf_atividade_colaboradores"
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.ForeignKey("sf_atividades_grupo.id"), nullable=False)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"), nullable=False)
    eh_responsavel = db.Column(db.Boolean, default=False)

    colaborador = db.relationship("Colaborador")


class AtividadeDia(db.Model):
    """Uma linha/dia da atividade (execução). status: PENDENTE (nada preenchido ainda) |
    AGUARDANDO_APROVACAO | APROVADA | ATRASADA (nada preenchido e a data já passou).
    [19/09] Para atividade tipo NORMAL: dias_restantes substitui a antiga % de conclusão —
    o colaborador informa quantos dias ainda faltam pra terminar. meta_percentual e
    percentual ficam mantidos no banco por compatibilidade histórica (RDOs/relatórios
    antigos que já os usavam), mas a lógica NOVA não os usa mais pra NORMAL.
    Para atividade tipo FIXA: nenhum dos dois se aplica — só fotos_json e
    descricao_execucao (sem percentual nem dias_restantes)."""
    __tablename__ = "sf_atividade_dias"
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.ForeignKey("sf_atividades_grupo.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    ordem = db.Column(db.Integer, nullable=False)     # 1, 2, 3... dentro do grupo
    meta_percentual = db.Column(db.Integer, nullable=False)   # [legado] não usado pra NORMAL desde 19/09
    percentual = db.Column(db.Integer)                # [legado] não usado pra NORMAL desde 19/09
    dias_restantes = db.Column(db.Integer)            # [19/09] o que o colaborador de fato reporta
    dias_restantes_esperado = db.Column(db.Integer)   # [19/09] o que seria esperado (dia_anterior - 1), pra auditoria
    descricao_execucao = db.Column(db.Text)
    justificativa_queda = db.Column(db.Text)          # obrigatório se a atividade cresceu além do previsto
    fotos_json = db.Column(db.Text)                   # até 4 fotos "depois/progresso" do dia
    status = db.Column(db.String(24), default="PENDENTE")
    reprogramado_de = db.Column(db.Date)               # data original, se foi reprogramada
    motivo_reprogramacao = db.Column(db.Text)
    aprovado_em = db.Column(db.DateTime)
    # [fix CRÍTICO 22/09] aprovado_por era uma FK única pra usuarios.id — mas quem aprova pode
    # ser um Colaborador (Encarregado logado normalmente, não via QR), cujo current_user.id é
    # o ID dele na tabela de COLABORADORES, não de usuários. Isso violava a FK e derrubava a
    # aprovação com erro 500 ("Key (aprovado_por)=(31) is not present in table usuarios").
    # Separado em duas colunas, mesmo padrão já usado em RelatorioAtividade/ExecucaoChecklist.
    aprovado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    aprovado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    retificado = db.Column(db.Boolean, default=False)
    gerado_por_crescimento = db.Column(db.Boolean, default=False)  # [19/09] esta linha nasceu de um report que precisou de mais dias
    aviso_conflito_agenda = db.Column(db.Text)  # [fix 22/09] antes só aparecia 1x pro colaborador; agora fica salvo e visível pro Encarregado na aprovação

    preenchimentos = db.relationship("RegistroPreenchimento", backref="dia",
                                     order_by="RegistroPreenchimento.criado_em",
                                     cascade="all, delete-orphan")

    @property
    def atrasada(self):
        return self.status == "PENDENTE" and self.data < date.today()

    @property
    def aprovado_por_nome(self):
        if self.aprovado_por_usuario_id:
            u = db.session.get(Usuario, self.aprovado_por_usuario_id)
            return u.nome if u else "—"
        if self.aprovado_por_colaborador_id:
            c = db.session.get(Colaborador, self.aprovado_por_colaborador_id)
            return c.nome if c else "—"
        return "—"


class HistoricoRetificacao(db.Model):
    """[23/09] Registra toda vez que um Encarregado (ou Admin) RETIFICA o que um colaborador
    apontou (dias_restantes, descrição) — guarda o valor ANTES e DEPOIS da mudança, e quem fez.
    Visível pro Admin a partir do RDO: clicar em "Ver" numa atividade específica mostra todas
    as edições feitas nela e por quem (pedido explícito do Antonio — antes a retificação
    simplesmente sobrescrevia o valor original sem deixar rastro)."""
    __tablename__ = "sf_historico_retificacao"
    id = db.Column(db.Integer, primary_key=True)
    dia_id = db.Column(db.ForeignKey("sf_atividade_dias.id"), nullable=False)
    dias_restantes_antes = db.Column(db.Integer)
    dias_restantes_depois = db.Column(db.Integer)
    descricao_antes = db.Column(db.Text)
    descricao_depois = db.Column(db.Text)
    retificado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    retificado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    dia = db.relationship("AtividadeDia", backref="historico_retificacoes")

    @property
    def retificado_por_nome(self):
        if self.retificado_por_colaborador_id:
            c = db.session.get(Colaborador, self.retificado_por_colaborador_id)
            return c.nome if c else "—"
        if self.retificado_por_usuario_id:
            u = db.session.get(Usuario, self.retificado_por_usuario_id)
            return u.nome if u else "—"
        return "—"


class RegistroPreenchimento(db.Model):
    """[v3] Histórico de QUEM preencheu a % de cada AtividadeDia (mais de um colaborador
    pode preencher a mesma atividade/dia ao longo do tempo — guardamos todos os registros,
    não só o valor final)."""
    __tablename__ = "sf_registros_preenchimento"
    id = db.Column(db.Integer, primary_key=True)
    dia_id = db.Column(db.ForeignKey("sf_atividade_dias.id"), nullable=False)
    colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    percentual = db.Column(db.Integer, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    colaborador = db.relationship("Colaborador")

    @property
    def autor_nome(self):
        if self.colaborador_id:
            c = db.session.get(Colaborador, self.colaborador_id)
            return c.nome if c else "—"
        if self.usuario_id:
            u = db.session.get(Usuario, self.usuario_id)
            return u.nome if u else "—"
        return "—"


# ============================================================================
# RELATÓRIO DIÁRIO DE OBRA (RDO) — puxa dados da Programação de Atividades
# ============================================================================

class RelatorioDiarioObra(db.Model):
    """[v4] Registro diário de campo/obra: mão de obra presente, atividades do dia (as que já
    estavam PROGRAMADAS para aquela data — não se escolhe manualmente), condições climáticas,
    equipamentos usados, e uma MÉDIA PONDERADA da % executada no dia (ponderada pela meta de
    cada atividade). Sobe para aprovação de um Encarregado E de um Admin — só sai de PENDENTE
    quando os dois aprovarem."""
    __tablename__ = "sf_rdo"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    planta_id = db.Column(db.ForeignKey("almox_plantas.id"), nullable=False)
    condicao_climatica = db.Column(db.String(80), nullable=False)
    horario_inicio = db.Column(db.String(5), default="07:00")   # [19/09] "HH:MM", editável
    horario_termino = db.Column(db.String(5), default="16:48")  # [19/09] "HH:MM", editável
    mao_de_obra_texto = db.Column(db.Text)      # lista livre (nome + função) por linha, pré-preenchida
    equipamentos_texto = db.Column(db.Text)      # equipamentos usados no dia, texto livre
    atividades_ids_json = db.Column(db.Text)     # ids de AtividadeGrupo daquele dia (automático)
    percentual_medio = db.Column(db.Float)        # média ponderada pela meta de cada atividade do dia
    observacoes = db.Column(db.Text)
    status = db.Column(db.String(20), default="PENDENTE")  # PENDENTE|APROVADO
    aprovado_encarregado_em = db.Column(db.DateTime)
    aprovado_encarregado_por = db.Column(db.ForeignKey("almox_colaboradores.id"))
    aprovado_admin_em = db.Column(db.DateTime)
    aprovado_admin_por = db.Column(db.ForeignKey("usuarios.id"))
    # [fix CRÍTICO 23/09] mesmo bug de criado_por como FK única — separado em duas colunas.
    criado_por_usuario_id = db.Column(db.ForeignKey("usuarios.id"))
    criado_por_colaborador_id = db.Column(db.ForeignKey("almox_colaboradores.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    planta = db.relationship("Planta")

    @property
    def atividades(self):
        import json as _json
        try:
            ids = _json.loads(self.atividades_ids_json or "[]")
        except (ValueError, TypeError):
            ids = []
        if not ids:
            return []
        return AtividadeGrupo.query.filter(AtividadeGrupo.id.in_(ids)).all()

    @property
    def totalmente_aprovado(self):
        return self.aprovado_encarregado_em is not None and self.aprovado_admin_em is not None



