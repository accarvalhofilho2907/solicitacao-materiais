"""Cria o usuário administrador inicial e (opcional) dados de exemplo.

Uso:
    python seed.py                      # cria admin a partir das variáveis de ambiente
    SEED_DEMO=1 python seed.py          # cria também tipos/fornecedores/usuário de exemplo
"""
import os

from app import create_app
from app.extensions import db
from app.models import Usuario, TipoMaterial, Fornecedor

app = create_app()

ADMIN_NOME = os.environ.get("SEED_ADMIN_NOME", "Administrador")
ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
ADMIN_SENHA = os.environ.get("SEED_ADMIN_SENHA", "admin123")

with app.app_context():
    db.create_all()

    if not Usuario.query.filter_by(email=ADMIN_EMAIL.lower()).first():
        a = Usuario(nome=ADMIN_NOME, email=ADMIN_EMAIL.lower(), papel="admin")
        a.set_senha(ADMIN_SENHA)
        db.session.add(a)
        print(f"Admin criado: {ADMIN_EMAIL} / senha: {ADMIN_SENHA}")
    else:
        print("Admin já existe.")

    if os.environ.get("SEED_DEMO") == "1":
        if not TipoMaterial.query.first():
            t_eletrico = TipoMaterial(nome="Elétrico")
            t_hidraulico = TipoMaterial(nome="Hidráulico")
            db.session.add_all([t_eletrico, t_hidraulico])
            db.session.flush()
            db.session.add(Fornecedor(nome="Eletro Fornecedora LTDA",
                                      email="vendas@eletro.example", tipos=[t_eletrico]))
            db.session.add(Fornecedor(nome="HidroMax",
                                      email="comercial@hidromax.example", tipos=[t_hidraulico]))
            if not Usuario.query.filter_by(email="solicitante@example.com").first():
                s = Usuario(nome="João Solicitante", email="solicitante@example.com")
                s.set_senha("solic123")
                db.session.add(s)
            print("Dados de exemplo criados (tipos, fornecedores, solicitante@example.com / solic123).")

    db.session.commit()
    print("OK.")
