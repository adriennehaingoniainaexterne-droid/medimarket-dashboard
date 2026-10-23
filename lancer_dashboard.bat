@echo off
REM Lance le dashboard PAARLY en double-cliquant ce fichier
title PAARLY Dashboard
cd /d "%~dp0"

echo ============================================================
echo  Demarrage du dashboard PAARLY...
echo  Le navigateur va s'ouvrir automatiquement sur http://localhost:8501
echo  Pour arreter : Ctrl+C ou fermer cette fenetre.
echo ============================================================
echo.

python -m streamlit run app.py

REM En cas d'erreur, la fenetre reste ouverte pour voir le message
echo.
echo ============================================================
echo  Le dashboard s'est arrete.
echo ============================================================
pause
