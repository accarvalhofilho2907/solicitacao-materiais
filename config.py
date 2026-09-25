import os
import re

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-troque-esta-chave")

    # Banco: usa DATABASE_URL (Postgres/Neon) se existir; senão SQLite local.
    # [25/09] A primeira tentativa de corrigir o erro "ModuleNotFoundError: No module
    # named 'psycopg'" (só fazia _db.startswith(...) num prefixo exato) NÃO resolveu em
    # produção — sinal de que a string colada no Render tem alguma variação que o match
    # exato não pegava (espaço/aspas sobrando na hora de colar, "postgres+psycopg://" sem
    # o "ql", maiúsculas, etc). Reescrito de forma bem mais defensiva: remove espaços e
    # aspas nas pontas, e usa regex (case-insensitive) pra normalizar QUALQUER variação de
    # prefixo que comece com "postgres" e mencione "psycopg" (sem o "2") logo em seguida,
    # forçando sempre "postgresql+psycopg2://" — o único driver que está instalado
    # (psycopg2-binary, requirements.txt). Também cobre o caso clássico "postgres://" sem
    # driver nenhum, que o SQLAlchemy 1.4+ não aceita mais sem o "ql".
    _db = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(basedir, "app.db"))
    _db = _db.strip().strip('"').strip("'")
    _db = re.sub(r"^postgres(ql)?(\+psycopg(?!2))?://", "postgresql+psycopg2://", _db,
                 count=1, flags=re.IGNORECASE)
    SQLALCHEMY_DATABASE_URI = _db
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Corrige "SSL connection has been closed unexpectedly" (Neon derruba conexões
    # ociosas do plano grátis; pool_pre_ping testa a conexão antes de usá-la e
    # pool_recycle descarta conexões "velhas" antes que o banco as feche sozinho).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Upload de imagens. Limite generoso porque o Relatório de Carga pode receber
    # várias fotos de celular (cada uma 3-5 MB). Configurável no Render pela variável
    # MAX_UPLOAD_MB sem precisar mexer no código. Padrão: 100 MB por requisição.
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(basedir, "uploads")
    ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

    # Armazenamento externo de imagens (produção). Se vazio, salva local.
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")

    # E-mail (SMTP). Se MAIL_HOST vazio, os e-mails só são registrados no log.
    MAIL_HOST = os.environ.get("MAIL_HOST")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USER = os.environ.get("MAIL_USER")
    MAIL_PASS = os.environ.get("MAIL_PASS")
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@solicitacoes.local")

    # Para onde vão os avisos de "nova solicitação"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")

    # URL base usada nos links dentro dos e-mails
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
