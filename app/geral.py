from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user

from .extensions import db
from .models import Sugestao
from .emails import enviar_email

geral_bp = Blueprint("geral", __name__)


@geral_bp.route("/faq")
@login_required
def faq():
    return render_template("geral/faq.html")


@geral_bp.route("/novidades")
@login_required
def novidades():
    return render_template("geral/novidades.html")


@geral_bp.route("/sugerir", methods=["GET", "POST"])
@login_required
def sugerir():
    if request.method == "POST":
        texto = request.form.get("texto", "").strip()
        if texto:
            sugestao = Sugestao(texto=texto)
            from .facilities import _marcar_autor
            _marcar_autor(sugestao, "autor")
            db.session.add(sugestao)
            db.session.commit()
            enviar_email(current_app.config.get("ADMIN_EMAIL"), "Nova sugestão de melhoria",
                         f"{current_user.nome} sugeriu:\n\n{texto}")
            flash("Obrigado! Sua sugestão foi enviada. 💡", "success")
            return redirect(url_for("geral.sugerir"))
        flash("Escreva sua sugestão.", "warning")
    return render_template("geral/sugerir.html")
