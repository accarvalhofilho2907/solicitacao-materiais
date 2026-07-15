from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from .extensions import db
from .models import Usuario, Colaborador

auth_bp = Blueprint("auth", __name__)


def _home_para(u):
    # Colaborador logado no sistema
    if isinstance(u, Colaborador):
        return url_for("almox.home") if u.pode_almox_modulo else url_for("solicitante.index")
    if u.is_admin:
        return url_for("admin.dashboard")
    # solicitante, almoxarifado e visualizador usam o painel do solicitante
    return url_for("solicitante.index")


@auth_bp.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect(_home_para(current_user))
    return redirect(url_for("auth.login"))


def _acha_por_email(email):
    u = Usuario.query.filter_by(email=email).first()
    if u:
        return u
    return (Colaborador.query.filter(Colaborador.email.isnot(None))
            .filter(db.func.lower(Colaborador.email) == email).first())


def _acha_por_cpf(cpf_digitos):
    """Colaborador cujo CPF (só dígitos) bate com o informado."""
    for c in Colaborador.query.filter(Colaborador.ativo.is_(True)).all():
        if "".join(ch for ch in (c.cpf or "") if ch.isdigit()) == cpf_digitos and cpf_digitos:
            return c
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ident = (request.form.get("email") or request.form.get("ident") or "").strip()
        senha = request.form.get("senha", "")
        obj = None
        if "@" in ident:
            obj = _acha_por_email(ident.lower())
        else:
            cpf = "".join(ch for ch in ident if ch.isdigit())
            obj = _acha_por_cpf(cpf) if cpf else None
        if obj is None:
            flash("CPF/e-mail ou senha inválidos.", "danger")
            return render_template("login.html")
        if not obj.ativo:
            flash("Acesso desativado. Procure o administrador.", "danger")
            return render_template("login.html")
        # Colaborador sem senha: primeiro acesso define a senha
        if isinstance(obj, Colaborador) and not obj.tem_senha:
            conf = request.form.get("confirma")
            if conf is None:
                return render_template("login.html", definir=True, ident=ident)
            if len(senha) < 4 or senha != conf:
                flash("Primeiro acesso: crie uma senha de ao menos 4 dígitos (iguais nos dois campos).", "warning")
                return render_template("login.html", definir=True, ident=ident)
            obj.set_senha(senha)
            db.session.commit()
            login_user(obj)
            return redirect(_home_para(obj))
        if obj.check_senha(senha):
            login_user(obj)
            if getattr(obj, "senha_temporaria", False):
                return redirect(url_for("auth.trocar_senha"))
            return redirect(_home_para(obj))
        flash("CPF/e-mail ou senha inválidos.", "danger")
    return render_template("login.html")


@auth_bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        nova = request.form.get("nova", "")
        conf = request.form.get("confirma", "")
        if len(nova) < 6:
            flash("A senha deve ter ao menos 6 caracteres.", "danger")
        elif nova != conf:
            flash("As senhas não coincidem.", "danger")
        else:
            current_user.set_senha(nova)
            current_user.senha_temporaria = False
            db.session.commit()
            flash("Senha atualizada.", "success")
            return redirect(_home_para(current_user))
    return render_template("trocar_senha.html")


@auth_bp.route("/trocar-tema", methods=["POST"])
@login_required
def trocar_tema():
    novo = request.form.get("tema")
    if novo not in ("claro", "escuro"):
        novo = "escuro" if current_user.tema_preferido == "claro" else "claro"
    current_user.tema_preferido = novo
    db.session.commit()
    destino = request.form.get("voltar") or request.referrer or url_for("auth.index")
    return redirect(destino)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.before_app_request
def _forcar_troca_senha():
    """Se a senha é temporária, obriga a trocar antes de usar o sistema."""
    if not current_user.is_authenticated or not current_user.senha_temporaria:
        return
    permitidos = {"auth.trocar_senha", "auth.logout", "static", "uploads"}
    if request.endpoint not in permitidos:
        return redirect(url_for("auth.trocar_senha"))
