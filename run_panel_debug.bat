@echo off
chcp 65001 >nul
cd /d %~dp0

:: ==========================================
::  ANTI-API - Servidor Web con Debug
::  Sistema Cookies Simple (Grok)
:: ==========================================

echo ==========================================
echo   ANTI-API - Iniciando Servidor
echo   Version: Sistema Cookies Simple (Grok)
echo ==========================================
echo.

:: Verificar Python
python --version >nul 2>&1
if ERRORLEVEL 1 (
  echo [ERROR] Python no esta instalado o no esta en PATH
  pause
  exit /b 1
)

:: Verificar/Instalar dependencias
echo [1/3] Verificando dependencias...
python -m pip install -q -r requirements.txt >nul 2>&1
if ERRORLEVEL 1 (
  echo [ERROR] No se pudieron instalar dependencias
  pause
  exit /b 1
)
echo      OK

:: Verificar Playwright
echo [2/3] Verificando Playwright...
python -c "from playwright.sync_api import sync_playwright" >nul 2>&1
if ERRORLEVEL 1 (
  echo      Instalando navegadores Playwright...
  python -m playwright install chromium
  if ERRORLEVEL 1 (
    echo [ERROR] No se pudo instalar Playwright
    pause
    exit /b 1
  )
)
echo      OK

:: Verificar directorios
echo [3/3] Verificando estructura...
if not exist cookies mkdir cookies
if not exist docs\debug mkdir docs\debug
echo      OK

echo.
echo ==========================================
echo   SERVIDOR WEB INICIANDO
echo   http://localhost:4000
echo ==========================================
echo.
echo   MODO DEBUG: Veras todo en el CMD
echo   Presiona Ctrl+C para detener
echo ==========================================
echo.

python app.py
