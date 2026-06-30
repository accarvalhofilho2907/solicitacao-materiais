from functools import wraps
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, abort, flash, current_app
from flask_login import login_required, current_user

from .extensions import db
from .models import Solicitacao
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
    if s.status == "AGUARDANDO_CHEGADA":
        s.status = "CONCLUIDO"
        s.chegada_confirmada_por = current_user.id
        s.chegada_em = datetime.utcnow()
        db.session.commit()
        enviar_email([s.solicitante.email, current_app.config.get("ADMIN_EMAIL")],
                     f"Solicitação Nº {s.id} — material recebido",
                     f"O almoxarifado confirmou a chegada do material da solicitação Nº {s.id} ({s.material}).")
        flash(f"Chegada confirmada. Solicitação Nº {s.id} concluída.", "success")
    else:
        flash("Esta solicitação não está aguardando chegada.", "warning")
    return redirect(url_for("almox.index"))
