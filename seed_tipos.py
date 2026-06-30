"""Cadastra os tipos de material padrão.

Idempotente: roda quantas vezes quiser, não cria duplicados.
Uso:  python seed_tipos.py
"""
from app import create_app
from app.extensions import db
from app.models import TipoMaterial

TIPOS = [
    "CONSUMIVEIS EM GERAL",
    "LINHA DE TRANSMISSÃO",
    "TI/INFORMATICA",
    "SOLDA EM GERAL",
    "PINTURA EM GERAL",
    "VIAS DE ACESSO EM GERAL",
    "REFRIGERAÇÃO EM GERAL",
    "FERRAMENTAS EM GERAL",
    "CUPIM - ESP",
    "VEICULO EM GERAL",
    "COPA E COZINHA EM GERAL",
    "BATERIAS/PILHAS EM GERAL",
    "UTENSILIOS EM GERAL",
    "BELZONA - ESP",
    "RESISTENCIAS DE AQUECIMENTO EM GERAL",
    "CONECTORES DE SUBESTAÇÃO EM GERAL",
    "MUFLAS/BOTINHAS/TERMINACOES",
    "EMBALAGENS EM GERAL",
    "SIEMENS - ESP",
    "WEG - ESP",
    "ELOS - ESP",
    "DELTA STAR - ESP",
    "MEGABRAS - ESP",
    "NANOPROTECH - ESP",
    "SALVI BR - ESP",
    "SADEL - ESP",
    "TREETECH - ESP",
    "TILUB - ESP",
    "BOBINAS MADEIRA EM GERAL",
    "ELETRONICA EM GERAL",
    "MERCADO LIVRE - ESP",
    "ROLAMENTOS EM GERAL",
]

app = create_app()

with app.app_context():
    novos = 0
    for nome in TIPOS:
        nome = nome.strip()
        if not TipoMaterial.query.filter_by(nome=nome).first():
            db.session.add(TipoMaterial(nome=nome))
            novos += 1
    db.session.commit()
    print(f"{novos} tipo(s) adicionado(s). Total de tipos cadastrados: {TipoMaterial.query.count()}.")
