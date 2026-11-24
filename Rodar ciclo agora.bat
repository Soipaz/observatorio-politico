@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist config.json (
  echo Primeira vez: vamos configurar seu estado e municipio.
  python -X utf8 observatorio.py configurar
)
echo Coletando dados oficiais... (alguns minutos)
python -X utf8 observatorio.py ciclo
echo.
start "" "%~dp0relatorios\ultimo.html"
pause
