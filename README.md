# ANTI-API - Acceso a Chats de IA via Web (sin API)

Sistema para interactuar con chats de IA web (Meta AI, Gemini, Grok) usando Playwright, simulando una API REST sin usar las APIs oficiales de pago.

**Versión Libre**: Sin sistema de cuentas, gestión simple de sesiones via cookies.

**Modo Puentear Login**: Usa cookies directamente sin verificar sesión previa (más rápido y menos detecciones).

## Inicio Rápido

### Opción 1: Ejecutar con el batch (Windows)

```bash
run_panel_debug.bat
```

### Opción 2: Ejecutar manualmente

```bash
pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Abre http://localhost:4000 en tu navegador.

## Sistema de Cookies (Formato Simple)

Este sistema usa cookies en formato **dict clave-valor** (estilo Grok system), mucho más simple que el formato array completo del navegador.

### Formatos soportados:

**1. Dict simple (recomendado):**
```json
{
  "__Secure-1PSID": "tu_valor_aqui",
  "__Secure-1PSIDTS": "tu_valor_aqui",
  "NID": "tu_valor_aqui"
}
```

**2. Array de cookies (también soportado):**
```json
[
  {"name": "__Secure-1PSID", "value": "xxx", "domain": ".google.com"},
  {"name": "NID", "value": "yyy", "domain": ".google.com"}
]
```

## Uso con Meta AI

### 1. Obtener Cookies de Meta

```bash
python get_cookies.py --model meta --output cookies_meta.json --wait 90
```

El navegador se abrirá en https://www.meta.ai/. Haz login con tu cuenta de Facebook/Meta, espera a que cargue el chat, y las cookies se guardarán automáticamente.

### 2. Enviar Prompt

1. Selecciona modelo "meta"
2. Pega las cookies en formato JSON simple
3. Escribe tu prompt
4. Haz clic en "Enviar prompt"

### Script de Prueba (CLI)

```bash
# Obtener cookies automáticamente
python get_cookies.py --model meta --output cookies_meta.json --wait 90

# Enviar prompt
python test_meta.py
```

## Uso con Gemini

### 1. Obtener Cookies de Gemini

**Opción A: Usar el helper (automático):**
```bash
python get_cookies.py --model gemini --output cookies_gemini.json --wait 90
```

**Opción B: Manual con extensión:**
1. Abre Chrome y ve a https://gemini.google.com
2. Inicia sesión con tu cuenta de Google
3. Instala la extensión **"Cookie Editor"** (Chrome Web Store)
4. Exporta las cookies y convierte a formato simple:
   ```bash
   # El helper get_cookies.py ya las convierte automáticamente
   # O usa el botón "Format" en Cookie Editor
   ```

### 2. Enviar Prompt

1. Selecciona modelo "gemini"
2. Pega las cookies en formato JSON simple
3. Escribe tu prompt
4. Haz clic en "Enviar prompt"

### Script de Prueba (CLI)

```bash
# Obtener cookies automáticamente
python get_cookies.py --model gemini --output cookies_gemini.json --wait 90

# Enviar prompt
python test_gemini.py --cookies cookies_gemini.json --prompt "Hola Gemini"
```

## Configuración de Modelos

Edita `models.json`:

```json
{
  "name": "gemini",
  "display_name": "Google Gemini",
  "url": "https://gemini.google.com/",
  "prompt_selector": "div[contenteditable='true']",
  "cookies_file": "cookies_gemini.json"
}
```

## Estructura

```
ANTI-API/
├── run_panel_debug.bat  # Arranque automático (Windows)
├── anti_api.py          # Core Playwright
├── app.py               # API Flask
├── get_cookies.py       # Helper para obtener cookies
├── test_gemini.py       # Test CLI
├── models.json          # Configuración modelos
├── templates/index.html # Panel web
└── static/app.js        # Frontend
```

## API REST

Accesible desde cualquier servicio externo (OpenCloud, bots, etc.)

### Autenticación
Configura `ANTI_API_KEY` en `.env`. Envía el header:
```
X-API-Key: tu_api_key
```
Peticiones desde `127.0.0.1` (panel local) no requieren key.

### Endpoints

**Health check:**
```bash
curl http://TU_IP:4000/api/status
```

**Enviar prompt (1 modelo):**
```bash
curl -X POST http://TU_IP:4000/api/send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu_api_key" \
  -d '{"model": "gemini", "prompt": "Hola"}'
```

**Batch — N prompts en paralelo (hasta 10 navegadores simultáneos):**
```bash
curl -X POST http://TU_IP:4000/api/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu_api_key" \
  -d '{
    "queries": [
      {"model": "gemini", "prompt": "¿Qué es Python?"},
      {"model": "grok",   "prompt": "Explica Docker"},
      {"model": "gemini", "prompt": "¿Qué es Kubernetes?"}
    ]
  }'
```

## Despliegue en Servidor (Linux)

```bash
git clone https://github.com/TU_USUARIO/ANTI-API.git
cd ANTI-API
cp .env.example .env     # Edita con tu API key
chmod +x start.sh
./start.sh
```

Para producción con `gunicorn`:
```bash
pip install gunicorn
./start.sh   # Detecta gunicorn automáticamente
```

## Configuración (.env)

```env
ANTI_API_KEY=tu_clave_secreta_aqui
ANTI_API_HOST=0.0.0.0
ANTI_API_PORT=4000
ANTI_API_MAX_PARALLEL=10
```

## Solución de Problemas

| Error | Solución |
|-------|----------|
| "No se encontró el campo de texto" | Cookies expiradas, obtén nuevas con `get_cookies.py` |
| "Cookies de Meta incompletas" | Copia cookies desde **facebook.com** (no meta.ai) |
| Timeout 120s | Cookies expiradas o modelo no respondió |
| "API key inválida" | Revisa header `X-API-Key` y `.env` |

## Logs

Automáticos en `logs/anti_api.log` (rotación a 5MB, 3 backups).

## Seguridad

- Las cookies contienen sesiones activas — **no las compartas**
- Configura `ANTI_API_KEY` antes de exponer el puerto
- Usa firewall/VPN en servidor de producción
