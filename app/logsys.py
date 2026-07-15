"""Log central do sistema. Registra ações de qualquer área com o ator atual
(usuário logado por e-mail OU colaborador logado por CPF), sem quebrar FKs."""
from flask_login import current_user

from .extensions import db
from .models import AlmoxLog, Usuario


def registrar(categoria, detalhe):
    """Grava uma linha no log do sistema. Nunca lança exceção para não travar a ação."""
    try:
        autor_id = None
        autor_nome = None
        if getattr(current_user, "is_authenticated", False):
            autor_nome = getattr(current_user, "nome", None)
            if isinstance(current_user, Usuario):
                autor_id = current_user.id
        db.session.add(AlmoxLog(autor_id=autor_id, autor_nome=autor_nome,
                                categoria=categoria, detalhe=(detalhe or "")[:400]))
    except Exception:
        pass
