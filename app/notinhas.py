from functools import wraps
from datetime import date, datetime
from collections import defaultdict

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from .extensions import db
from .models import Notinha, Fornecedor, Atividade

notinhas_bp = Blueprint("notinhas", __name__, url_prefix="/notinhas")


def _pode(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if not (current_user.is_admin or current_user.is_almox):
            abort(403)
        return f(*a, **k)
    return w


def _ini_mes():
    return date.today().replace(day=1)


@notinhas_bp.route("/")
@_pode
def index():
    notas = Notinha.query.order_by(Notinha.data.desc(), Notinha.id.desc()).limit(100).all()
    do_mes = Notinha.query.filter(Notinha.data >= _ini_mes()).all()
    por_forn = defaultdict(float)
    total_mes = 0.0
    for n in do_mes:
        por_forn[n.fornecedor.nome] += float(n.valor)
        total_mes += float(n.valor)
    por_forn = sorted(por_forn.items(), key=lambda x: -x[1])
    return render_template("notinhas/index.html", notas=notas, por_forn=por_forn, total_mes=total_mes,
                           hoje=date.today().isoformat(),
                           fornecedores=Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome_fantasia).all(),
                           atividades=Atividade.query.filter_by(ativo=True).order_by(Atividade.nome).all())


@notinhas_bp.route("/nova", methods=["POST"])
@_pode
def nova():
    try:
        valor = float(request.form.get("valor", "0").replace(".", "").replace(",", "."))
    except ValueError:
        valor = 0
    fid = request.form.get("fornecedor_id")
    data_str = request.form.get("data") or date.today().isoformat()
    if not fid or valor <= 0:
        flash("Informe fornecedor e um valor válido.", "danger")
        return redirect(url_for("notinhas.index"))
    db.session.add(Notinha(
        data=datetime.strptime(data_str, "%Y-%m-%d").date(),
        fornecedor_id=int(fid),
        atividade_id=request.form.get("atividade_id") or None,
        valor=valor,
        criado_por=current_user.id,
    ))
    db.session.commit()
    flash("Notinha lançada.", "success")
    return redirect(url_for("notinhas.index"))
