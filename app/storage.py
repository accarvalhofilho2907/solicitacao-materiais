import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXT"]


def salvar_imagem(file_storage):
    """Salva uma imagem e devolve a URL. Usa Cloudinary se configurado; senão, disco local."""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed(file_storage.filename):
        return None

    if current_app.config.get("CLOUDINARY_URL"):
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(secure=True)  # lê CLOUDINARY_URL do ambiente
        res = cloudinary.uploader.upload(file_storage, folder="solicitacoes")
        return res["secure_url"]

    # Fallback local
    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    nome = secure_filename(file_storage.filename)
    nome = f"{uuid.uuid4().hex}_{nome}"
    file_storage.save(os.path.join(pasta, nome))
    return f"/uploads/{nome}"
