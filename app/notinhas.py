from functools import wraps
from datetime import date, datetime
from collections import defaultdict

from flask import (Blueprint, render_template, redirect, url_for, request, flash, abort, Response, jsonify)
from flask_login import login_required, current_user

from .extensions import db, csrf
from .models import Notinha, Fornecedor, Atividade
from .pdf import gerar_pdf_notinhas

notinhas_bp = Blueprint("notinhas", __name__, url_prefix="/notinhas")


def _pode(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if not (current_user.is_admin or current_user.is_almox):
            abort(403)
        return f(*a, **k)
    return w


def _parse_valor(s):
    """Aceita só números e vírgula (sem ponto). Ex.: '1.234,50' inválido; '1234,50' ok."""
    s = (s or "").strip()
    s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _competencia_de(data_str):
    return data_str[:7] if data_str else date.today().strftime("%Y-%m")


def _parse_valor_filtro(s):
    v = _parse_valor(s)
    return v


def _filtra(q):
    f_de = request.args.get("de")
    f_ate = request.args.get("ate")
    f_forn = request.args.get("fornecedor")
    f_ativ = request.args.get("atividade")
    f_vmin = request.args.get("valor_min")
    f_vmax = request.args.get("valor_max")
    if f_de:
        q = q.filter(Notinha.data >= datetime.strptime(f_de, "%Y-%m-%d").date())
    if f_ate:
        q = q.filter(Notinha.data <= datetime.strptime(f_ate, "%Y-%m-%d").date())
    if f_forn:
        q = q.filter_by(fornecedor_id=int(f_forn))
    if f_ativ:
        q = q.filter_by(atividade_id=int(f_ativ))
    vmin = _parse_valor_filtro(f_vmin)
    vmax = _parse_valor_filtro(f_vmax)
    if vmin is not None:
        q = q.filter(Notinha.valor >= vmin)
    if vmax is not None:
        q = q.filter(Notinha.valor <= vmax)
    return q, f_de, f_ate, f_forn, f_ativ, f_vmin, f_vmax


@notinhas_bp.route("/")
@_pode
def index():
    q, f_de, f_ate, f_forn, f_ativ, f_vmin, f_vmax = _filtra(Notinha.query)
    notas = q.order_by(Notinha.data.desc(), Notinha.id.desc()).all()
    # Totais por fornecedor (com base no filtro aplicado)
    por_forn = defaultdict(float)
    total = 0.0
    for n in notas:
        por_forn[n.fornecedor.nome] += float(n.valor)
        total += float(n.valor)
    por_forn = sorted(por_forn.items(), key=lambda x: -x[1])
    # Total do mês corrente (sempre)
    ini = date.today().replace(day=1)
    total_mes = sum(float(n.valor) for n in Notinha.query.filter(Notinha.data >= ini).all())
    return render_template("notinhas/index.html", notas=notas, por_forn=por_forn, total=total,
                           total_mes=total_mes, hoje=date.today().isoformat(),
                           f_de=f_de, f_ate=f_ate, f_forn=f_forn, f_ativ=f_ativ,
                           f_vmin=f_vmin, f_vmax=f_vmax,
                           fornecedores=Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome_fantasia).all(),
                           atividades=Atividade.query.filter_by(ativo=True).order_by(Atividade.nome).all())


@notinhas_bp.route("/nova", methods=["POST"])
@_pode
def nova():
    valor = _parse_valor(request.form.get("valor"))
    fid = request.form.get("fornecedor_id")
    aid = request.form.get("atividade_id")
    data_str = request.form.get("data") or date.today().isoformat()
    if not fid or not aid or valor is None or valor <= 0:
        flash("Preencha Data, Fornecedor, Atividade e Valor (use só números e vírgula).", "danger")
        return redirect(url_for("notinhas.index"))
    comp = _competencia_de(data_str)   # competência sempre derivada da data (item 79)
    db.session.add(Notinha(
        data=datetime.strptime(data_str, "%Y-%m-%d").date(), competencia=comp,
        fornecedor_id=int(fid), atividade_id=int(aid), valor=valor, criado_por=current_user.id))
    db.session.commit()
    flash("Notinha lançada.", "success")
    return redirect(url_for("notinhas.index"))


@notinhas_bp.route("/<int:nid>/editar", methods=["POST"])
@_pode
def editar(nid):
    n = db.session.get(Notinha, nid) or abort(404)
    valor = _parse_valor(request.form.get("valor"))
    if valor is None or valor <= 0:
        flash("Valor inválido (use só números e vírgula).", "danger")
        return redirect(url_for("notinhas.index"))
    data_str = request.form.get("data") or n.data.isoformat()
    n.data = datetime.strptime(data_str, "%Y-%m-%d").date()
    n.competencia = _competencia_de(data_str)   # competência sempre derivada da data (item 79)
    if request.form.get("fornecedor_id"):
        n.fornecedor_id = int(request.form["fornecedor_id"])
    if request.form.get("atividade_id"):
        n.atividade_id = int(request.form["atividade_id"])
    n.valor = valor
    db.session.commit()
    flash("Notinha atualizada.", "success")
    return redirect(url_for("notinhas.index"))


@notinhas_bp.route("/<int:nid>/excluir", methods=["POST"])
@_pode
def excluir(nid):
    n = db.session.get(Notinha, nid) or abort(404)
    db.session.delete(n)
    db.session.commit()
    flash("Notinha excluída.", "success")
    return redirect(url_for("notinhas.index"))


@notinhas_bp.route("/atividade-rapida", methods=["POST"])
@_pode
@csrf.exempt
def atividade_rapida():
    """Cadastro inline de Atividade nas Notinhas (item 78) — almox e admin."""
    nome = ((request.json or {}).get("nome", "") if request.is_json else request.form.get("nome", "")).strip().upper()
    if not nome:
        return jsonify(ok=False, erro="nome vazio"), 400
    a = Atividade.query.filter(db.func.upper(Atividade.nome) == nome).first()
    if not a:
        a = Atividade(nome=nome)
        db.session.add(a)
        db.session.commit()
    return jsonify(ok=True, id=a.id, nome=a.nome)


@notinhas_bp.route("/exportar")
@_pode
def exportar():
    q, *_ = _filtra(Notinha.query)
    notas = q.order_by(Notinha.data).all()
    pdf = gerar_pdf_notinhas(notas)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=notinhas.pdf"})
