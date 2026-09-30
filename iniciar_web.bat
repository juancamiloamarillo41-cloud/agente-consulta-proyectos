@echo off
rem Lanzador de la interfaz web: doble clic para arrancarla y abrir el navegador.
rem Usa el Python del entorno virtual del proyecto, asi que no hace falta activarlo.
title Agente de consulta de proyectos
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv en esta carpeta.
    echo Sigue los pasos de instalacion del README y vuelve a intentarlo.
    pause
    exit /b 1
)

rem Si no hay clave de Gemini, la pide en esta ventana, la valida y crea el archivo .env.
".venv\Scripts\python.exe" -m project_agent.setup_env
if errorlevel 1 (
    pause
    exit /b 1
)

if not exist "data\fichas.db" (
    echo Creando la base de fichas a partir de data\fichas\*.json ...
    ".venv\Scripts\python.exe" -c "from project_agent.storage.repository import rebuild_db_from_json; rebuild_db_from_json()"
)

".venv\Scripts\python.exe" -m project_agent.web %*
if errorlevel 1 pause
