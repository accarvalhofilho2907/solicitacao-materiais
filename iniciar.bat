@echo off
title Solicitacao de Materiais - Servidor
cd /d "%~dp0"

REM Cria o ambiente virtual na primeira vez
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente pela primeira vez...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Verificando dependencias...
python -m pip install -q -r requirements.txt

echo.
echo ============================================
echo  Sistema iniciando em http://localhost:5000
echo  Para PARAR: feche esta janela ou tecle Ctrl+C
echo ============================================
echo.

REM Abre o navegador e sobe o servidor
start "" http://localhost:5000
python wsgi.py

pause
