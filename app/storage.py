import os
import uuid
from io import BytesIO

from flask import current_app
from werkzeug.utils import secure_filename

try:
    from PIL import Image as PILImage, ImageOps, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True   # uploads de celular às vezes vêm truncados
    _TEM_PIL = True
except Exception:
    _TEM_PIL = False


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXT"]


def _comprimir_imagem(file_storage, max_lado=1600, quality=78):
    """[compressão] Reduz o tamanho da foto ANTES de subir pro Cloudinary — sem isso, fotos de
    celular (2-8MB cada, sem compressão) esgotam rápido os 25 créditos/mês do plano Free
    (1 crédito = 1GB de armazenamento). Mesma técnica já validada no relatório de carga
    (draft() evita estourar RAM ao decodificar fotos de 12-48MP; exif_transpose corrige
    rotação vinda do celular). 1600px/q78 fica bem menor que os 2400px/q90 do relatório de
    carga (que precisa de mais nitidez para impressão) — aqui a foto é só registro/evidência,
    então prioriza tamanho de arquivo sobre resolução máxima.
    Devolve (bytes_jpeg, nome_arquivo) ou (None, None) se não for possível comprimir (nesse
    caso o chamador deve usar o arquivo original como fallback, não travar o upload)."""
    if not _TEM_PIL:
        return None, None
    im = None
    try:
        im = PILImage.open(file_storage.stream)
        try:
            im.draft("RGB", (max_lado, max_lado))
        except Exception:
            pass
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if max(im.size) > max_lado:
            im.thumbnail((max_lado, max_lado))
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        out.seek(0)
        nome_base = secure_filename(file_storage.filename or "foto")
        nome_base = os.path.splitext(nome_base)[0] + ".jpg"
        return out, nome_base
    except Exception:
        return None, None
    finally:
        try:
            if im is not None:
                im.close()
        except Exception:
            pass
        try:
            file_storage.stream.seek(0)   # devolve o ponteiro pro chamador poder usar o original se precisar
        except Exception:
            pass


def salvar_imagem(file_storage):
    """Salva uma imagem e devolve a URL. Usa Cloudinary se configurado; senão, disco local.
    Comprime a foto antes de salvar (reduz ~85-95% do tamanho) — importante porque o plano
    gratuito do Cloudinary conta armazenamento em créditos limitados, e o disco local do
    Render é volátil (não é feito pra guardar arquivo grande de qualquer forma)."""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed(file_storage.filename):
        return None

    comprimido, nome_comprimido = _comprimir_imagem(file_storage)
    usar_arquivo = comprimido if comprimido is not None else file_storage
    nome_final = nome_comprimido if comprimido is not None else file_storage.filename

    if current_app.config.get("CLOUDINARY_URL"):
        try:
            import cloudinary
            import cloudinary.uploader
            from urllib.parse import urlparse

            # [fix CRÍTICO 23/09] cloudinary.config(secure=True) SEM passar as credenciais
            # confia que a biblioteca já leu CLOUDINARY_URL do os.environ — mas ela só faz
            # essa leitura UMA VEZ, na importação do módulo (Config() é instanciado no nível
            # do módulo, em cloudinary/__init__.py). Se o Render não reiniciar de fato TODOS
            # os workers do Gunicorn depois de uma mudança na variável de ambiente, um worker
            # antigo continua com a config velha em memória pra sempre — explica por que
            # algumas requisições funcionavam e outras não, mesmo com a variável já corrigida
            # no painel. Aqui fazemos o parse manual (só urlparse, biblioteca padrão) e
            # passamos cloud_name/api_key/api_secret explicitamente — usa sempre o valor
            # ATUAL de current_app.config, nunca o que estava em memória na importação.
            parsed = urlparse(current_app.config["CLOUDINARY_URL"])
            cloudinary.config(cloud_name=parsed.hostname, api_key=parsed.username,
                              api_secret=parsed.password, secure=True)
            res = cloudinary.uploader.upload(usar_arquivo, folder="solicitacoes")
            return res["secure_url"]
        except Exception:
            # [fix] CLOUDINARY_URL configurada errada (ex.: valor de exemplo "<your_api_key>"
            # colado por engano) ou serviço fora do ar não pode derrubar a página inteira com
            # 500 — cai para o disco local (mesmo sendo volátil, é melhor que quebrar o salvar).
            current_app.logger.exception("Falha ao enviar imagem pro Cloudinary; usando fallback local.")
            if hasattr(usar_arquivo, "seek"):
                usar_arquivo.seek(0)

    # Fallback local
    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    nome = secure_filename(nome_final)
    nome = f"{uuid.uuid4().hex}_{nome}"
    caminho = os.path.join(pasta, nome)
    if comprimido is not None:
        with open(caminho, "wb") as f:
            f.write(comprimido.getvalue())
    else:
        file_storage.save(caminho)
    return f"/uploads/{nome}"
