"""Define antonio.carvalho@srna.co como ÚNICO administrador.

- Cria o usuário admin se não existir (senha provisória, trocada no 1º acesso).
- Remove o privilégio de admin dos demais (rebaixa para 'solicitante') —
  não apaga as contas para não perder o histórico de solicitações.

Uso:  python definir_admin.py
"""
import os

from app import create_app
from app.extensions import db
from app.models import Usuario

ADMIN_EMAIL = "antonio.carvalho@srna.co"
SENHA_PROVISORIA = os.environ.get("ADMIN_SENHA_PROVISORIA", "Trocar@123")

app = create_app()

with app.app_context():
    eu = Usuario.query.filter_by(email=ADMIN_EMAIL).first()
    if not eu:
        eu = Usuario(nome="Antonio Carvalho", email=ADMIN_EMAIL, papel="admin", senha_temporaria=True)
        eu.set_senha(SENHA_PROVISORIA)
        db.session.add(eu)
        print(f"Admin criado: {ADMIN_EMAIL} / senha provisória: {SENHA_PROVISORIA} (troca no 1º acesso)")
    else:
        eu.papel = "admin"
        eu.ativo = True
        print(f"{ADMIN_EMAIL} definido como admin.")

    rebaixados = 0
    for u in Usuario.query.filter_by(papel="admin").all():
        if u.email != ADMIN_EMAIL:
            u.papel = "solicitante"
            rebaixados += 1
            print(f"  - {u.email}: admin -> solicitante")
    db.session.commit()
    print(f"OK. {rebaixados} outro(s) administrador(es) rebaixado(s). Admin único: {ADMIN_EMAIL}.")
