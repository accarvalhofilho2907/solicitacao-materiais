title Solicitacao de Materiais - Servidor
cd /d "%~dp0"

echo ============================================
echo  Iniciando... (nao feche esta janela)
echo ============================================

REM Verifica Python 3.12
py -3.12 --version
if errorlevel 1 (
  echo.
  echo [ERRO] Python 3.12 nao encontrado. Rode:  py install 3.12
  echo.
  pause
  exit /b 1
)

REM Cria o ambiente virtual na primeira vez
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente pela primeira vez...
  py -3.12 -m venv .venv
)

echo Verificando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERRO] Falha ao instalar dependencias. Veja as mensagens acima.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================
echo  Sistema iniciando em http://localhost:5000
echo  Para PARAR: feche esta janela ou tecle Ctrl+C
echo ============================================
echo.

start "" http://localhost:5000
".venv\Scripts\python.exe" wsgi.py

echo.
echo [O servidor foi encerrado. Se fechou sozinho, o erro aparece acima.]
pause
