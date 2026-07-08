import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-troque-esta-chave")

    # Banco: usa DATABASE_URL (Postgres/Neon) se existir; senão SQLite local.
    _db = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(basedir, "app.db"))
    if _db.startswith("postgres://"):
        _db = _db.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Corrige "SSL connection has been closed unexpectedly" (Neon derruba conexões
    # ociosas do plano grátis; pool_pre_ping testa a conexão antes de usá-la e
    # pool_recycle descarta conexões "velhas" antes que o banco as feche sozinho).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Upload de imagens
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB por requisição
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
