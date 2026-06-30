import smtplib
import logging
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger("emails")


def enviar_email(destinatarios, assunto, corpo, anexo_bytes=None, anexo_nome=None):
    """Envia e-mail via SMTP. Se MAIL_HOST não estiver configurado, só registra no log."""
    if destinatarios is None:
        destinatarios = []
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return

    cfg = current_app.config
    if not cfg.get("MAIL_HOST"):
        log.info("[E-MAIL SIMULADO] Para: %s | Assunto: %s\n%s", destinatarios, assunto, corpo)
        print(f"[E-MAIL SIMULADO] Para: {destinatarios} | Assunto: {assunto}")
        return

    msg = EmailMessage()
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = ", ".join(destinatarios)
    # Respostas dos fornecedores voltam para o e-mail do admin
    if cfg.get("ADMIN_EMAIL"):
        msg["Reply-To"] = cfg["ADMIN_EMAIL"]
    msg["Subject"] = assunto
    msg.set_content(corpo)
    if anexo_bytes:
        msg.add_attachment(
            anexo_bytes, maintype="application", subtype="pdf",
            filename=anexo_nome or "pedido.pdf",
        )

    with smtplib.SMTP(cfg["MAIL_HOST"], cfg["MAIL_PORT"]) as s:
        s.starttls()
        if cfg.get("MAIL_USER"):
            s.login(cfg["MAIL_USER"], cfg["MAIL_PASS"])
        s.send_message(msg)
