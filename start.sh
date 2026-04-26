#!/bin/bash
# ==========================================
#  ANTI-API — Servidor de producción (Linux)
#  Ejecutar: chmod +x start.sh && ./start.sh
# ==========================================

set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "  ANTI-API — Iniciando Servidor"
echo "=========================================="

# 1. Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 no está instalado"
    exit 1
fi

# 2. Crear virtualenv si no existe
if [ ! -d "venv" ]; then
    echo "[1/4] Creando virtualenv..."
    python3 -m venv venv
fi

# 3. Activar e instalar dependencias
echo "[2/4] Instalando dependencias..."
source venv/bin/activate
pip install -q -r requirements.txt

# 4. Instalar navegador Playwright
echo "[3/4] Verificando Playwright..."
python -c "from playwright.sync_api import sync_playwright" 2>/dev/null || {
    echo "      Instalando navegadores Playwright..."
    playwright install chromium
    playwright install-deps chromium 2>/dev/null || true
}

# 5. Crear directorios
echo "[4/4] Verificando estructura..."
mkdir -p cookies logs docs/debug

echo ""
echo "=========================================="
echo "  SERVIDOR INICIANDO"
echo "  http://0.0.0.0:4000"
echo "=========================================="
echo ""

# Producción: usar gunicorn si está disponible
if command -v gunicorn &> /dev/null || pip show gunicorn &> /dev/null 2>&1; then
    echo "  Modo: Gunicorn (producción)"
    gunicorn app:app \
        --bind 0.0.0.0:4000 \
        --workers 1 \
        --threads 12 \
        --timeout 300 \
        --access-logfile logs/access.log \
        --error-logfile logs/error.log
else
    echo "  Modo: Flask dev (instala gunicorn para producción)"
    python app.py
fi
