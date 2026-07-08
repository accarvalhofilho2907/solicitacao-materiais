from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from .extensions import db
from .models import Usuario

auth_bp = Blueprint("auth", __name__)


def _home_para(u):
    if u.is_admin:
        return url_for("admin.dashboard")
    # solicitante, almoxarifado e visualizador usam o painel do solicitante
    return url_for("solicitante.index")


@auth_bp.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect(_home_para(current_user))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        u = Usuario.query.filter_by(email=email).first()
        if u and u.ativo and u.check_senha(senha):
            login_user(u)
            if u.senha_temporaria:
                return redirect(url_for("auth.trocar_senha"))
            return redirect(_home_para(u))
        flash("E-mail ou senha inválidos.", "danger")
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
