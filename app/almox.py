from functools import wraps
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, abort, flash, current_app, request
from flask_login import login_required, current_user

from .extensions import db
from .models import Solicitacao, LogSolicitacao
from .emails import enviar_email

almox_bp = Blueprint("almox", __name__, url_prefix="/almoxarifado")


def almox_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not (current_user.is_almox or current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@almox_bp.route("/chegadas")
@almox_required
def index():
    pendentes = (Solicitacao.query.filter_by(status="AGUARDANDO_CHEGADA")
                 .order_by(Solicitacao.prazo_recebimento).all())
    recentes = (Solicitacao.query.filter_by(status="CONCLUIDO")
                .order_by(Solicitacao.chegada_em.desc()).limit(10).all())
    return render_template("almox/index.html", pendentes=pendentes, recentes=recentes)


@almox_bp.route("/chegada/<int:sid>", methods=["POST"])
@almox_required
def marcar_chegada(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    if s.status != "AGUARDANDO_CHEGADA":
        flash("Esta solicitação não está aguardando chegada.", "warning")
        return redirect(url_for("almox.index"))
    ja = s.quantidade_recebida or 0
    restante = max(s.quantidade - ja, 0)
    # quantidade informada nesta confirmação (padrão = restante)
    try:
        qtd = int(request.form.get("qtd_recebida") or restante)
    except ValueError:
        qtd = restante
    if qtd <= 0:
        flash("Informe uma quantidade recebida maior que zero.", "danger")
        return redirect(url_for("almox.index"))
    qtd = min(qtd, restante)
    total = ja + qtd
    s.quantidade_recebida = total
    if total >= s.quantidade:
        s.status = "CONCLUIDO"
        s.chegada_confirmada_por = current_user.id
        s.chegada_em = datetime.utcnow()
        evento = f"Chegada confirmada — recebido {total} de {s.quantidade} (Concluído)"
        assunto = f"Solicitação Nº {s.id} — material recebido (completo)"
        msg = f"Chegada completa: {total} de {s.quantidade} ({s.material})."
        flash(f"Chegada total confirmada. Solicitação Nº {s.id} concluída.", "success")
    else:
        evento = f"Chegada parcial — recebido {qtd} (acumulado {total} de {s.quantidade})"
        assunto = f"Solicitação Nº {s.id} — chegada parcial"
        msg = f"Chegada parcial: recebido {total} de {s.quantidade} ({s.material})."
        flash(f"Chegada parcial registrada: {total} de {s.quantidade}.", "success")
    db.session.add(LogSolicitacao(solicitacao_id=s.id, autor_id=current_user.id, evento=evento))
    db.session.commit()
    enviar_email([s.solicitante.email, current_app.config.get("ADMIN_EMAIL")], assunto,
                 f"A confirmação de chegada da solicitação Nº {s.id} foi registrada. {msg}")
    return redirect(url_for("almox.index"))
