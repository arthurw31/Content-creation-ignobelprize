@echo off
REM Double-clique ce fichier pour lancer le pipeline.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\start.py
  goto :eof
)
where python >nul 2>nul
if %errorlevel%==0 (
  python scripts\start.py
  goto :eof
)
echo Python 3 n'est pas installe.
echo Telecharge-le ici : https://www.python.org/downloads/
echo Coche bien "Add Python to PATH" pendant l'installation.
pause
