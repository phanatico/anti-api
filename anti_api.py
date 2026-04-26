"""
ANTI-API - Sistema de automatización de chats de IA
Replicación exacta del sistema Grok (IVAN-VIDEO-NEW!!!!!!)
Soporta cookies en formato simple JSON clave-valor

Arquitectura (idéntica a Grok):
  - 1 instancia = 1 Chrome browser (por cookie set)
  - Cookies se inyectan en TODOS los dominios configurados
  - Solo 4 campos por cookie: name, value, domain, path
  - Headless por defecto, sin abrir navegador visible
  - Typing via keyboard.type(delay=20) como Grok
  - Submit via JS evaluate como Grok
  - Extracción de respuesta via JS específico por modelo
"""

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from playwright.sync_api import sync_playwright

# Configurar logging — consola + archivo automático
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "anti_api.log")

_fmt = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')

_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(_fmt)
_console.setLevel(logging.DEBUG)

from logging.handlers import RotatingFileHandler
_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
_file_handler.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[_console, _file_handler])
log = logging.getLogger("AntiAPI")
log.info(f"Log file: {LOG_FILE}")

# ════════════════════════════════════════════════════════
#  CONFIGURACIÓN DE COOKIES POR MODELO
#  Replicado de grok_playwright_source.py
# ════════════════════════════════════════════════════════
MODEL_COOKIE_CONFIG = {
    "grok": {
        "cookie_names": ["sso", "sso-rw", "x-userid", "i18nextLng"],
        "domains": [".grok.com", ".x.ai"],
        "url": "https://grok.com",
    },
    "gemini": {
        "cookie_names": ["__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-1PAPISID",
                         "__Secure-3PSID", "NID", "SIDCC", "APISID", "HSID", "SID"],
        "domains": [".google.com"],
        "url": "https://gemini.google.com",
    },
    "meta": {
        "cookie_names": ["c_user", "xs", "datr", "fr", "sb", "presence", "wd", "usida"],
        "domains": [".meta.ai", ".facebook.com"],
        "url": "https://www.meta.ai",
    },
}


def _sanitize_cookie_value(val: str) -> str:
    """
    Sanitiza valor de cookie para evitar Invalid cookie fields.
    Elimina caracteres de control, newlines, y null bytes.
    """
    if not val:
        return ""
    # Eliminar null bytes y caracteres de control
    val = re.sub(r'[\x00-\x1f\x7f]', '', val)
    # Eliminar newlines
    val = val.replace('\n', '').replace('\r', '')
    # Truncar a 4096 chars (límite de Chrome)
    if len(val) > 4096:
        val = val[:4096]
    return val


def normalize_cookies(cookie_input: Union[Dict, List]) -> Dict[str, str]:
    """
    Normaliza cookies a dict simple clave-valor.
    Soporta dict simple o array de cookies del navegador.
    """
    if isinstance(cookie_input, dict):
        # Si todos los valores son strings, devolver tal cual
        if all(isinstance(v, str) for v in cookie_input.values()):
            return cookie_input
        # Si hay valores no-string, convertirlos
        result = {}
        for k, v in cookie_input.items():
            if isinstance(v, str):
                result[k] = v
            else:
                result[k] = str(v)
        return result
    elif isinstance(cookie_input, list):
        result = {}
        for item in cookie_input:
            if isinstance(item, dict) and "name" in item and "value" in item:
                result[item["name"]] = str(item["value"])
        return result
    return {}


class AntiApiChat:
    """
    Cliente de chat usando Playwright.
    Replicación exacta del sistema Grok.

    Uso:
        chat = AntiApiChat(url="https://grok.com", model_name="grok",
                           headless=True, cookies={"sso": "xxx", "sso-rw": "yyy"})
        chat.start()
        response = chat.send_prompt("Hola")
        chat.close()
    """

    def __init__(
        self,
        url: str,
        model_name: str = "generic",
        headless: bool = True,
        cookies: Optional[Dict[str, str]] = None,
        input_selector: Optional[str] = None,
        timeout: int = 60,
    ):
        self.url = url
        self.model_name = model_name.lower()
        self.headless = headless
        self.cookies = cookies or {}
        self.input_selector = input_selector
        self.timeout = timeout

        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None
        self._started = False  # Track if start() was called

        # Para Meta AI: captura de respuestas de red
        self._meta_response_chunks: List[str] = []
        self._meta_response_lock = threading.Lock()

    # ════════════════════════════════════════════════════════
    #  LIFECYCLE (idéntico a Grok)
    # ════════════════════════════════════════════════════════
    def start(self) -> None:
        """Inicia el navegador e inyecta cookies. Idéntico a GrokConverter.start()"""
        if self._started:
            log.info(f"[{self.model_name}] Browser already started, reusing...")
            return

        log.info(f"[{self.model_name}] Starting browser (headless={self.headless})...")

        self._pw = sync_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--incognito",           # Fresh session como Grok
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--disable-default-apps",
            "--window-size=1280,800",
            "--window-position=0,0",
        ]

        try:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=launch_args,
            )
        except Exception as e:
            self._pw.stop()
            if "executable" in str(e).lower() or "not found" in str(e).lower():
                raise RuntimeError("Chrome no instalado. Descarga desde google.com/chrome")
            raise

        self._ctx = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        # Inyectar cookies EXACTAMENTE como Grok
        self._inject_cookies()

        # NO crear page aquí - send_prompt() creará una nueva página cada vez
        self._started = True
        log.info(f"[{self.model_name}] Browser ready (context created)")

    def _inject_cookies(self) -> None:
        """
        Inyecta cookies en TODOS los dominios configurados.
        EXACTAMENTE como Grok: usa TODAS las cookies proporcionadas, sin filtrar.
        Solo 4 campos: name, value, domain, path.
        """
        if not self.cookies:
            log.warning(f"[{self.model_name}] No cookies provided")
            return

        config = MODEL_COOKIE_CONFIG.get(self.model_name, {})
        domains = config.get("domains", ["." + self.url.split("/")[2].replace("www.", "")])

        # USAR TODAS LAS COOKIES - sin filtrar por cookie_names
        # Esto es idéntico al comportamiento del sistema Grok original
        all_cookie_names = list(self.cookies.keys())
        log.debug(f"[{self.model_name}] Cookies disponibles: {all_cookie_names}")

        # Cookies que requieren secure=True y sameSite="None" (prefijo __Secure-)
        # Chrome rechaza estas cookies sin esos flags vía CDP
        SECURE_PREFIXES = ("__Secure-", "__Host-")

        # Construir cookie_list inyectando cada cookie en cada dominio (como Grok)
        cookie_list = []
        for name in all_cookie_names:
            val = self.cookies.get(name)
            if val:
                val = _sanitize_cookie_value(str(val))
                if not val:
                    continue
                is_secure = any(name.startswith(p) for p in SECURE_PREFIXES)
                for domain in domains:
                    entry = {
                        "name": name,
                        "value": val,
                        "domain": domain,
                        "path": "/",
                    }
                    if is_secure:
                        entry["secure"] = True
                        entry["sameSite"] = "None"
                    cookie_list.append(entry)

        if not cookie_list:
            raise ValueError(f"No valid cookies to inject. Available: {list(self.cookies.keys())}")

        try:
            self._ctx.add_cookies(cookie_list)
            unique_names = list(set(c["name"] for c in cookie_list))
            log.info(f"[{self.model_name}] {len(cookie_list)} cookies injected "
                     f"({len(unique_names)} unique): {', '.join(unique_names)}")
        except Exception as e:
            log.error(f"[{self.model_name}] Cookie injection failed: {e}")
            # Intentar inyectar una por una para aislar el problema
            success_count = 0
            for c in cookie_list:
                try:
                    self._ctx.add_cookies([c])
                    success_count += 1
                except Exception as ce:
                    log.warning(f"   Cookie '{c['name']}' failed: {ce}")
            log.info(f"[{self.model_name}] Partial injection: {success_count}/{len(cookie_list)} cookies")

    def close(self) -> None:
        """Cierra navegador y libera recursos. Idéntico a GrokConverter.stop()"""
        try:
            if self._ctx: self._ctx.close()
            if self._browser: self._browser.close()
            if self._pw: self._pw.stop()
        except:
            pass
        self._ctx = self._browser = self._pw = self.page = None
        log.info(f"[{self.model_name}] Browser closed")

    # ════════════════════════════════════════════════════════
    #  NAVIGATION (idéntico a Grok)
    # ════════════════════════════════════════════════════════
    def _navigate(self) -> None:
        """Navega a la URL y espera a que cargue el campo de entrada."""
        log.info(f"[{self.model_name}] Navigating to {self.url}...")
        self.page.goto(self.url, wait_until="domcontentloaded", timeout=30000)

        # DETECCIÓN TEMPRANA: Verificar si redirigió a login por URL
        current_url = self.page.url
        # Solo URLs de login reales (no buscar "login" en HTML que da falsos positivos)
        login_urls = {
            "grok":   ["x.com/i/flow", "twitter.com/i/flow"],
            "gemini": ["accounts.google.com/signin", "accounts.google.com/v3"],
            "meta":   ["facebook.com/login", "facebook.com/checkpoint"],
        }
        model_login_urls = login_urls.get(self.model_name, [])
        if any(ind in current_url.lower() for ind in model_login_urls):
            log.error(f"[{self.model_name}] ❌ REDIRIGIDO A LOGIN: {current_url}")
            raise RuntimeError(f"Cookies inválidas - redirigido a login: {current_url}")

        # Esperar a que JS renderice
        self.page.wait_for_timeout(1500)

        # Intentar encontrar input con cada selector
        selectors = self._get_input_selectors()
        for sel in selectors:
            try:
                self.page.wait_for_selector(sel, timeout=8000)
                log.info(f"[{self.model_name}] Page ready (input found: {sel})")
                return
            except Exception:
                continue

        # Si no se encontró input, verificar si es landing/login por contenido JS
        is_login = self.page.evaluate("""() => {
            const url = window.location.href.toLowerCase();
            const body = (document.body ? document.body.innerText : '').slice(0, 3000);
            // Solo detectar login si NO hay ningún input de chat visible
            const hasInput = document.querySelector(
                'div[contenteditable="true"], textarea, [role="textbox"]'
            );
            if (hasInput) return false;
            // Patrones claros de página de login (sin input = no logueado)
            if (body.includes('Sign in to') && body.includes('password')) return true;
            if (body.includes('Log in') && body.includes('Sign up') && body.length < 2000) return true;
            return false;
        }""")

        if is_login:
            log.error(f"[{self.model_name}] ❌ PÁGINA DE LOGIN DETECTADA (sin input de chat)")
            raise RuntimeError("Cookies inválidas - página muestra login en lugar del chat")

        log.error(f"[{self.model_name}] Input not found after trying all selectors")
        raise RuntimeError("Input not found — cookies inválidas o selectores desactualizados")

    def _get_input_selectors(self) -> List[str]:
        """Selectores de campo de entrada por modelo."""
        selectors = {
            "grok": [
                'div.ProseMirror[contenteditable="true"]',
                'div[contenteditable="true"][class*="ProseMirror"]',
                'div[contenteditable="true"][class*="tiptap"]',
                'div[contenteditable="true"]',
            ],
            "gemini": [
                'div[contenteditable="true"]',
                'textarea',
                'div[role="textbox"]',
                'rich-textarea div[contenteditable="true"]',
                '.ql-editor[contenteditable="true"]',
            ],
            "meta": [
                'div[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"]',
                'div[data-testid="chat-input"]',
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="Ask"]',
                'textarea',
            ],
        }
        result = selectors.get(self.model_name, ['div[contenteditable="true"]', 'textarea'])
        if self.input_selector:
            result.insert(0, self.input_selector)
        return result

    # ════════════════════════════════════════════════════════
    #  PROMPT TYPING (idéntico a Grok _type_prompt)
    # ════════════════════════════════════════════════════════
    def _type_prompt(self, prompt: str) -> bool:
        """
        Escribe el prompt en el campo de entrada.
        Usa JavaScript directo para mayor fiabilidad.
        """
        selectors = self._get_input_selectors()
        log.info(f"[{self.model_name}] Typing prompt...")

        # MÉTODO 1: Intentar con JavaScript directo (más fiable)
        js_result = self.page.evaluate("""
            ({selectors, text}) => {
                for (const sel of selectors) {
                    try {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            // Verificar que sea un input de chat (visible, habilitado, en viewport)
                            const rect = el.getBoundingClientRect();
                            const isVisible = rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight;
                            const isEnabled = !el.disabled && !el.getAttribute('disabled');

                            if (isVisible && isEnabled) {
                                // Intentar diferentes métodos de input
                                el.focus();
                                el.click();

                                // Para contenteditable
                                if (el.contentEditable === 'true') {
                                    el.innerHTML = '';
                                    const textNode = document.createTextNode(text);
                                    el.appendChild(textNode);
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    return { success: true, method: 'contenteditable', selector: sel };
                                }

                                // Para textarea/input
                                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                                    el.value = text;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    return { success: true, method: 'input', selector: sel };
                                }
                            }
                        }
                    } catch (e) {}
                }
                return { success: false };
            }
        """, {"selectors": selectors, "text": prompt})

        if js_result and js_result.get('success'):
            log.info(f"[{self.model_name}] Prompt typed via JS ({js_result.get('method')}: {js_result.get('selector')})")
            self.page.wait_for_timeout(500)
            return True

        # MÉTODO 2: Fallback con Playwright keyboard
        log.debug(f"[{self.model_name}] JS method failed, trying keyboard...")
        for sel in selectors:
            try:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    el.scroll_into_view_if_needed()
                    el.click(force=True, timeout=3000)
                    self.page.wait_for_timeout(300)

                    # Seleccionar todo y borrar
                    self.page.keyboard.press("Control+a")
                    self.page.wait_for_timeout(100)
                    self.page.keyboard.press("Backspace")
                    self.page.wait_for_timeout(200)

                    # Escribir
                    self.page.keyboard.type(prompt, delay=20)
                    self.page.wait_for_timeout(500)

                    log.info(f"[{self.model_name}] Prompt typed via keyboard ({len(prompt)} chars)")
                    return True
            except Exception as e:
                log.debug(f"[{self.model_name}] Keyboard method failed for {sel}: {e}")
                continue

        log.error(f"[{self.model_name}] Could not type prompt — no input found")
        return False

    # ════════════════════════════════════════════════════════
    #  SUBMIT (idéntico a Grok _click_submit via JS evaluate)
    # ════════════════════════════════════════════════════════
    def _click_submit(self) -> bool:
        """
        Click en botón submit via JS evaluate (como Grok).
        Espera hasta 3s a que el botón esté habilitado.
        """
        self.page.wait_for_timeout(1000)

        # Esperar a que el botón esté habilitado (como Grok)
        for _ in range(30):
            ready = self.page.evaluate("""() => {
                const btn = document.querySelector('button[type="submit"]');
                if (!btn) return false;
                return !btn.disabled && !btn.hasAttribute('disabled')
                    && btn.offsetParent !== null;
            }""")
            if ready:
                break
            self.page.wait_for_timeout(100)

        # Click via JS (idéntico a Grok)
        clicked = self.page.evaluate("""() => {
            const selectors = [
                'button[type="submit"]',
                'button[aria-label*="send" i]',
                'button[aria-label*="submit" i]',
                'button[aria-label="Enviar"]',
                'button[aria-label="Send"]',
                'button[aria-label*="Send message" i]',
            ];
            for (const sel of selectors) {
                const buttons = document.querySelectorAll(sel);
                for (const btn of buttons) {
                    if (btn.disabled || btn.hasAttribute('disabled')) continue;
                    if (btn.offsetParent === null) continue;
                    btn.click();
                    return sel;
                }
            }
            return null;
        }""")

        self.page.wait_for_timeout(2000)
        if clicked:
            log.info(f"[{self.model_name}] Submit clicked ({clicked})")
            return True

        # Fallback: Enter key (como Grok)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(2000)
        log.info(f"[{self.model_name}] Submit via Enter key")
        return True

    # ════════════════════════════════════════════════════════
    #  META AI: INTERCEPTACIÓN DE RED
    # ════════════════════════════════════════════════════════
    def _setup_meta_network_intercept(self) -> None:
        """
        Intercepta respuestas de red de Meta AI para capturar texto de la IA.
        Meta usa GraphQL + streaming RSC (React Server Components).
        Capturamos las respuestas de /api/graphql y streams de texto.
        """
        with self._meta_response_lock:
            self._meta_response_chunks = []

        def on_response(response):
            url = response.url
            # Capturar respuestas relevantes de Meta AI
            if any(p in url for p in [
                "/api/graphql",
                "meta.ai/api",
                "llama",
                "ai_response",
                "stream",
            ]):
                try:
                    if response.status == 200:
                        try:
                            body = response.body()
                            text = body.decode("utf-8", errors="replace")
                            if len(text) > 50:
                                log.debug(f"[meta] Network response captured from {url[:80]}: {len(text)} chars")
                                with self._meta_response_lock:
                                    self._meta_response_chunks.append(text)
                        except Exception as e:
                            log.debug(f"[meta] Could not read network response body: {e}")
                except Exception as e:
                    log.debug(f"[meta] Network intercept error: {e}")

        self.page.on("response", on_response)
        log.debug("[meta] Network intercept setup done")

    def _parse_meta_network_response(self) -> str:
        """
        Parsea los chunks de red capturados de Meta AI para extraer el texto de respuesta.
        Meta usa varios formatos: JSON GraphQL, RSC streaming.
        """
        with self._meta_response_lock:
            chunks = list(self._meta_response_chunks)

        if not chunks:
            log.debug("[meta] No network chunks captured")
            return ""

        log.debug(f"[meta] Parsing {len(chunks)} network chunks")

        best_text = ""

        for chunk in chunks:
            # Intentar parsear como JSON de GraphQL
            try:
                data = json.loads(chunk)
                # Meta GraphQL: data.data.node.bot_response_message.composed_text.content
                text = self._extract_meta_graphql_json(data)
                if text and len(text) > len(best_text):
                    best_text = text
                    log.debug(f"[meta] Extracted from GraphQL JSON: {len(text)} chars")
                    continue
            except json.JSONDecodeError:
                pass

            # Intentar parsear como NDJSON (líneas JSON)
            text = self._extract_meta_ndjson(chunk)
            if text and len(text) > len(best_text):
                best_text = text
                log.debug(f"[meta] Extracted from NDJSON: {len(text)} chars")
                continue

            # Intentar extraer de RSC streaming (__next_f.push)
            text = self._extract_meta_rsc_stream(chunk)
            if text and len(text) > len(best_text):
                best_text = text
                log.debug(f"[meta] Extracted from RSC stream: {len(text)} chars")

        return best_text

    def _extract_meta_graphql_json(self, data: Any) -> str:
        """Extrae texto de respuesta de un JSON de GraphQL de Meta."""
        if not isinstance(data, dict):
            return ""

        # Buscar recursivamente campos de texto que parecen respuestas de IA
        TEXT_FIELDS = ["bot_response_message", "composed_text", "display_text",
                       "message", "text", "response", "content", "ai_message"]

        def search(obj, depth=0):
            if depth > 10:
                return ""
            if isinstance(obj, str) and len(obj) > 50:
                return obj
            if isinstance(obj, dict):
                for key in TEXT_FIELDS:
                    if key in obj:
                        result = search(obj[key], depth + 1)
                        if result and len(result) > 50:
                            return result
                # Buscar en todos los valores
                for v in obj.values():
                    result = search(v, depth + 1)
                    if result and len(result) > 50:
                        return result
            if isinstance(obj, list):
                for item in obj:
                    result = search(item, depth + 1)
                    if result and len(result) > 50:
                        return result
            return ""

        return search(data)

    def _extract_meta_ndjson(self, text: str) -> str:
        """Extrae texto de respuesta de NDJSON (JSON Lines) de Meta."""
        best = ""
        for line in text.split('\n'):
            line = line.strip()
            if not line or not (line.startswith('{') or line.startswith('[')):
                continue
            try:
                data = json.loads(line)
                result = self._extract_meta_graphql_json(data)
                if result and len(result) > len(best):
                    best = result
            except:
                pass
        return best

    def _extract_meta_rsc_stream(self, text: str) -> str:
        """
        Extrae texto de un stream RSC de Next.js (React Server Components).
        El formato es líneas como: 0:{"a":"$@1","f":...}
        o scripts con self.__next_f.push([...])
        """
        best = ""

        # Buscar patrones de self.__next_f.push([N, "...texto..."])
        # o 0:texto directo del stream RSC
        patterns = [
            # RSC streaming format
            r'\d+:(\{.*\})\n?',
            r'\d+:"([^"]{50,})"',
            # Next.js RSC push
            r'__next_f\.push\(\[.*?"([^"]{50,})"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                # Si es JSON, intentar extraer texto
                if match.startswith('{'):
                    try:
                        data = json.loads(match)
                        result = self._extract_meta_graphql_json(data)
                        if result and len(result) > len(best):
                            best = result
                        continue
                    except:
                        pass
                # Es texto directo
                # Limpiar escapes JSON
                cleaned = match.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                if len(cleaned) > len(best) and not any(x in cleaned for x in ['<script', 'function(', 'window.__']):
                    best = cleaned

        return best

    # ════════════════════════════════════════════════════════
    #  WAIT FOR RESPONSE
    # ════════════════════════════════════════════════════════
    def _get_response_selectors(self) -> List[str]:
        """Selectores para detectar texto de respuesta, específicos por modelo."""
        selectors_map = {
            "grok": [
                '.markdown',
                '.prose',
                '[data-message-author-role="assistant"]',
                'div[class*="message-content"]',
            ],
            # Gemini: NO usamos selectores simples porque el sidebar también
            # tiene model-response (historial). El wait usa lógica especial.
            "gemini": [
                "GEMINI_SPECIAL",
            ],
            "meta": [
                # Meta AI: intentamos DOM primero, luego red
                'div[data-testid="ai-response"]',
                'div[data-testid="bot-message"]',
                'div[class*="assistant"]',
                'div[dir="auto"]',
            ],
        }
        return selectors_map.get(self.model_name, [
            '[data-message-author-role="assistant"]',
            '.markdown', '.prose',
            'div[class*="message-content"]',
        ])

    def _wait_for_response(self, max_wait: int = 120) -> None:
        """
        Espera a que la respuesta aparezca y se estabilice.
        Polling cada 1s, detecta cuando el texto deja de cambiar.
        Usa selectores específicos por modelo.
        """
        log.info(f"[{self.model_name}] Waiting for response...")

        selectors = self._get_response_selectors()
        import json as _json
        selectors_js = _json.dumps(selectors)

        # JS especial para Gemini: busca en el área de conversación activa,
        # excluyendo el sidebar con historial de chats anteriores
        GEMINI_WAIT_JS = """
        () => {
            // Gemini: la conversación activa está en el área principal
            // Excluimos el nav sidebar izquierdo (chat-list)
            const exclude = (el) => {
                return !!el.closest('nav, side-nav-v2, .conversations-container, mat-sidenav');
            };
            const els = document.querySelectorAll('model-response, message-content, .response-container-content');
            let best = 0;
            for (const el of els) {
                if (exclude(el)) continue;
                const text = (el.innerText || '').trim();
                // Excluir si es solo UI label
                if (text.length > best && !text.startsWith('Defining') && text.length > 30) {
                    best = text.length;
                }
            }
            return best;
        }
        """

        # JS para Meta AI: busca respuesta en el DOM principal
        META_WAIT_JS = """
        () => {
            const isInput = (el) => !!el.closest('[contenteditable], textarea, input, form');
            const UI_PHRASES = ['Log in', 'Sign up', 'Ask Meta AI', 'Pregúntale a Meta', 'How can I help'];
            const isUI = (text) => UI_PHRASES.some(p => text.includes(p));

            // Buscar por data-testid específicos de Meta
            const testIds = ['ai-response', 'bot-message', 'assistant-message'];
            for (const tid of testIds) {
                const els = document.querySelectorAll(`[data-testid="${tid}"]`);
                if (els.length > 0) {
                    const text = (els[els.length - 1].innerText || '').trim();
                    if (text.length > 30 && !isUI(text)) return text.length;
                }
            }

            // Buscar en dir="auto" fuera de inputs
            const dirEls = Array.from(document.querySelectorAll('[dir="auto"]'))
                .filter(el => !isInput(el));
            for (let i = dirEls.length - 1; i >= 0; i--) {
                const text = (dirEls[i].innerText || '').trim();
                if (text.length > 50 && !isUI(text)) return text.length;
            }

            return 0;
        }
        """

        stable_count = 0
        prev_len = 0
        start_time = time.time()
        dump_done = False

        while time.time() - start_time < max_wait:
            try:
                if self.model_name == "gemini":
                    current_len = self.page.evaluate(GEMINI_WAIT_JS)
                elif self.model_name == "meta":
                    # Para Meta: verificar DOM y también si ya tenemos chunks de red
                    dom_len = self.page.evaluate(META_WAIT_JS)
                    with self._meta_response_lock:
                        net_len = sum(len(c) for c in self._meta_response_chunks)
                    current_len = max(dom_len, net_len // 10)  # red normalmente es 10x el texto real
                else:
                    current_len = self.page.evaluate(f"""
                        () => {{
                            const selectors = {selectors_js};
                            for (const sel of selectors) {{
                                const els = document.querySelectorAll(sel);
                                if (els.length > 0) {{
                                    const text = (els[els.length - 1].innerText || '').trim();
                                    if (text.length > 20) return text.length;
                                }}
                            }}
                            return 0;
                        }}""")

                if current_len > 50 and current_len == prev_len:
                    stable_count += 1
                    if stable_count >= 3:
                        log.info(f"[{self.model_name}] Response ready ({current_len} chars, stable)")
                        return
                else:
                    stable_count = 0

                prev_len = current_len

                # Si llevamos 10s sin detectar nada, hacer dump HTML para debug
                elapsed = time.time() - start_time
                if elapsed > 10 and current_len == 0 and not dump_done:
                    dump_done = True
                    try:
                        html = self.page.evaluate("() => document.body ? document.body.innerHTML.slice(0, 6000) : 'NO BODY'")
                        log.debug(f"[{self.model_name}] HTML DUMP (primeros 6000 chars) URL={self.page.url}:\n{html}")
                    except Exception as de:
                        log.debug(f"[{self.model_name}] HTML dump failed: {de}")

            except Exception:
                pass

            time.sleep(1)

        log.warning(f"[{self.model_name}] Response wait timeout after {max_wait}s")

    # ════════════════════════════════════════════════════════
    #  EXTRACT RESPONSE (JS específico por modelo)
    # ════════════════════════════════════════════════════════
    def _extract_response(self) -> str:
        """
        Extrae la última respuesta del asistente via JS.
        Usa extractores específicos por modelo.
        """
        log.info(f"[{self.model_name}] Extracting response...")

        # Extractor específico por modelo
        extractors = {
            "grok": self._extract_grok,
            "gemini": self._extract_gemini,
            "meta": self._extract_meta,
        }

        extractor = extractors.get(self.model_name, self._extract_generic)
        response = extractor()

        if response:
            log.info(f"[{self.model_name}] Response extracted ({len(response)} chars)")
            log.debug(f"   Preview: {response[:150]}...")
        else:
            log.error(f"[{self.model_name}] No response extracted")

        return response

    def _extract_grok(self) -> str:
        """Extractor específico para Grok."""
        return self.page.evaluate("""() => {
            // Grok usa markdown para las respuestas
            const selectors = [
                '.markdown',
                '.prose',
                '[data-message-author-role="assistant"]',
                'div[class*="message-content"]',
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    const last = els[els.length - 1];
                    const text = (last.innerText || last.textContent || '').trim();
                    if (text.length > 20) return text;
                }
            }
            return '';
        }""")

    def _extract_gemini(self) -> str:
        """Extractor específico para Gemini."""
        # Siempre hacer dump del HTML para depuración
        try:
            url = self.page.url
            html = self.page.evaluate("() => document.body ? document.body.innerHTML.slice(0, 8000) : ''")
            log.debug(f"[gemini] URL={url} HTML DUMP (primeros 8000 chars):\n{html}")
        except Exception:
            pass

        result = self.page.evaluate("""() => {
            const UI_PHRASES = [
                'Gemini can make mistakes', 'Gemini no es humano',
                'puede cometer errores', 'verifica sus respuestas',
                'Iniciar sesión', 'Sign in', 'Nueva conversación', 'New conversation',
                'Usar micrófono', 'Use microphone', 'Mostrar menú', 'Añadir archivos',
                'Try Gemini Advanced', 'Get more done',
            ];
            const isUI = (text) => UI_PHRASES.some(p => text.includes(p)) && text.length < 500;

            // Excluir solo sidebar de navegación (NO filtrar por "history")
            const inSidebar = (el) => !!el.closest(
                'nav, side-nav-v2, .conversations-container, mat-sidenav'
            );

            // Gemini usa Web Components: model-response, message-content
            const candidates = Array.from(document.querySelectorAll(
                'model-response, message-content, .response-container-content, .model-response-text'
            )).filter(el => !inSidebar(el));

            // Buscar el MEJOR candidato (más largo), no solo el último
            let bestText = '';
            for (const el of candidates) {
                const text = (el.innerText || el.textContent || '').trim();
                if (text.length > bestText.length && text.length > 30 && !isUI(text)) {
                    bestText = text;
                }
            }
            if (bestText) return bestText;

            // Fallback 2: buscar en .ql-editor, rich-textarea (el área de conversación)
            const convEls = document.querySelectorAll(
                '.conversation-container [class*="response"], ' +
                '.conversation-container [class*="model"], ' +
                'message-content'
            );
            for (const el of convEls) {
                if (inSidebar(el)) continue;
                const text = (el.innerText || el.textContent || '').trim();
                if (text.length > bestText.length && text.length > 30 && !isUI(text)) {
                    bestText = text;
                }
            }
            if (bestText) return bestText;

            // Fallback 3: párrafos <p> fuera del sidebar con texto largo
            const ps = Array.from(document.querySelectorAll('p'))
                .filter(el => !inSidebar(el));
            let collected = [];
            for (let i = ps.length - 1; i >= 0; i--) {
                const text = (ps[i].innerText || '').trim();
                if (text.length < 10) break;
                collected.unshift(text);
                if (collected.join(' ').length > 200) break;
            }
            if (collected.length > 0) {
                const joined = collected.join('\\n').trim();
                if (!isUI(joined)) return joined;
            }

            // Fallback 4: último recurso — cualquier div con mucho texto
            const allDivs = Array.from(document.querySelectorAll('div'))
                .filter(el => !inSidebar(el) && !el.closest('[contenteditable], textarea'));
            for (let i = allDivs.length - 1; i >= 0; i--) {
                const text = (allDivs[i].innerText || '').trim();
                // Solo si tiene texto real y no es demasiado largo (evitar containers padres)
                if (text.length > 50 && text.length < 10000 && !isUI(text)) {
                    // Verificar que no es un container padre gigante
                    if (allDivs[i].children.length < 20) return text;
                }
            }

            return '';
        }""")

        if not result:
            log.warning(f"[gemini] Extraction returned empty. Trying innerText of full page...")
            # Último recurso absoluto: evaluar qué hay en la página
            debug_info = self.page.evaluate("""() => {
                const modelResp = document.querySelectorAll('model-response');
                const msgContent = document.querySelectorAll('message-content');
                const allText = (document.body.innerText || '').slice(0, 500);
                return {
                    modelResponseCount: modelResp.length,
                    msgContentCount: msgContent.length,
                    modelResponseTexts: Array.from(modelResp).map(e => (e.innerText||'').slice(0,100)),
                    msgContentTexts: Array.from(msgContent).map(e => (e.innerText||'').slice(0,100)),
                    bodyPreview: allText
                };
            }""")
            log.debug(f"[gemini] Page debug: {debug_info}")

        return result or ""

    def _extract_meta(self) -> str:
        """
        Extractor para Meta AI.
        Prioridad:
        1. Datos capturados de la red (GraphQL/streaming) — más fiable
        2. DOM del chat activo — fallback

        Siempre hace dump HTML en DEBUG para poder ajustar selectores.
        """
        # Prioridad 1: datos de red interceptados
        net_text = self._parse_meta_network_response()
        if net_text and len(net_text) > 30:
            log.info(f"[meta] Using network-captured response ({len(net_text)} chars)")
            return net_text

        # Prioridad 2: DOM
        try:
            url = self.page.url
            html_dump = self.page.evaluate("() => document.body ? document.body.innerHTML.slice(-8000) : 'NO BODY'")
            log.debug(f"[meta] URL={url} HTML DUMP (últimos 8000 chars):\n{html_dump}")
        except Exception as e:
            log.debug(f"[meta] HTML dump failed: {e}")

        result = self.page.evaluate("""() => {
            const UI_PHRASES = [
                'Log in', 'Sign up', 'Create account',
                'Iniciar sesión', 'Crear cuenta',
                'Ask Meta AI', 'Pregúntale a Meta AI',
                'How can I help', 'Cómo puedo ayudarte',
                'Meta AI may make mistakes',
                'Envía comentarios',
            ];
            // Suggestion chips / starters que Meta muestra en la home
            const SUGGESTION_CHIPS = [
                'Crear elementos de acción', 'Transcribe notas',
                'Describe lo que está pasando', 'Crea una imagen',
                'Edita la imagen adjunta', 'Genera un sticker',
                'Create action items', 'Transcribe handwritten',
                'Describe what is happening', 'Create an image',
            ];
            const isUI = (text) => {
                if (UI_PHRASES.some(p => text.includes(p)) && text.length < 600) return true;
                // Textos muy cortos que coinciden con chips de sugerencia
                if (text.length < 80 && SUGGESTION_CHIPS.some(p => text.includes(p))) return true;
                return false;
            };
            const isInput = (el) => !!el.closest('[contenteditable], textarea, input, form');
            // Excluir suggestion starters
            const isStarter = (el) => !!el.closest('[data-testid*="starter"], [data-testid*="suggestion"], [class*="starter"], [class*="Starter"], [class*="suggestion"]');

            // ── Estrategia 1: data-testid conocidos ─────────────────
            const testIds = [
                'ai-response', 'bot-message', 'assistant-message',
                'response-message', 'message-ai', 'llm-response',
                'ai-message-content', 'response-content',
            ];
            for (const tid of testIds) {
                const els = document.querySelectorAll(`[data-testid="${tid}"]`);
                if (els.length > 0) {
                    const text = (els[els.length - 1].innerText || '').trim();
                    if (text.length > 20 && !isUI(text)) return text;
                }
            }

            // ── Estrategia 2: Buscar dentro del chat principal
            // Meta AI envuelve la conversación en un contenedor principal
            // Buscamos el último bloque de mensaje de la IA
            const chatContainers = [
                '[data-testid="chat-thread"]',
                '[data-testid="conversation"]',
                '[class*="ChatThread"]',
                '[class*="conversation"]',
                'main',
            ];
            for (const containerSel of chatContainers) {
                const container = document.querySelector(containerSel);
                if (!container) continue;

                // Dentro del contenedor, buscar el último mensaje de la IA
                // por dir="auto" fuera de inputs
                const dirEls = Array.from(container.querySelectorAll('[dir="auto"]'))
                    .filter(el => !isInput(el) && !isStarter(el) && (el.innerText || '').trim().length > 30);
                if (dirEls.length > 0) {
                    for (let i = dirEls.length - 1; i >= 0; i--) {
                        const text = (dirEls[i].innerText || '').trim();
                        if (text.length > 30 && !isUI(text)) return text;
                    }
                }
            }

            // ── Estrategia 3: dir="auto" en párrafos dentro de un contenedor
            // que no sea el input. Meta envuelve respuestas en <div dir="auto">
            const dirEls = Array.from(document.querySelectorAll('[dir="auto"]'))
                .filter(el => !isInput(el) && !isStarter(el) && (el.innerText || '').trim().length > 30);
            if (dirEls.length > 0) {
                // El último elemento con dir=auto que no sea UI
                for (let i = dirEls.length - 1; i >= 0; i--) {
                    const text = (dirEls[i].innerText || '').trim();
                    if (text.length > 30 && !isUI(text)) return text;
                }
            }

            // ── Estrategia 4: role="row" o role="gridcell" — Meta a veces usa grid
            for (const role of ['gridcell', 'listitem', 'article']) {
                const els = document.querySelectorAll(`[role="${role}"]`);
                for (let i = els.length - 1; i >= 0; i--) {
                    const text = (els[i].innerText || '').trim();
                    if (text.length > 30 && !isUI(text) && !isInput(els[i])) return text;
                }
            }

            // ── Estrategia 5: párrafos <p> fuera del input ──────────
            const ps = Array.from(document.querySelectorAll('p'))
                .filter(el => !isInput(el));
            // Agrupar párrafos consecutivos al final (la última respuesta)
            if (ps.length > 0) {
                let group = [];
                for (let i = ps.length - 1; i >= 0; i--) {
                    const text = (ps[i].innerText || '').trim();
                    if (text.length < 5) break;
                    group.unshift(text);
                    if (group.join(' ').length > 100) break;
                }
                const joined = group.join('\\n').trim();
                if (joined.length > 30 && !isUI(joined)) return joined;
            }

            return '';
        }""")

        if not result:
            log.error(f"[meta] No se extrajo respuesta. URL={self.page.url}")
        return result or ""

    def _extract_generic(self) -> str:
        """Extractor genérico para modelos no específicos."""
        return self.page.evaluate("""() => {
            const selectors = [
                '[data-message-author-role="assistant"]',
                '.markdown',
                '.prose',
                'div[class*="response"]',
                'div[class*="message-content"]',
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    const text = (els[els.length - 1].innerText || '').trim();
                    if (text.length > 20) return text;
                }
            }
            return '';
        }""")

    # ════════════════════════════════════════════════════════
    #  SESSION VALIDATION
    # ════════════════════════════════════════════════════════
    def check_session(self) -> Tuple[bool, str]:
        """
        Verifica que la sesión esté activa.
        Replicado de GrokConverter.validate_session().
        """
        page = self._ctx.new_page()
        try:
            page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            url = page.url
            login_urls = {
                "grok":   ["x.com/i/flow", "twitter.com/i/flow"],
                "gemini": ["accounts.google.com/signin", "accounts.google.com/v3"],
                "meta":   ["facebook.com/login", "facebook.com/checkpoint"],
            }
            model_login_urls = login_urls.get(self.model_name, [])
            if any(ind in url.lower() for ind in model_login_urls):
                return False, f"Redirected to login: {url}"

            # Verificaciones específicas por modelo
            if self.model_name == "gemini":
                return self._check_gemini_session(page)
            elif self.model_name == "meta":
                return self._check_meta_session(page)

            # Buscar campo de entrada (genérico)
            input_selectors = self._get_input_selectors()
            for sel in input_selectors:
                try:
                    page.wait_for_selector(sel, timeout=10000)
                    return True, "OK"
                except:
                    continue

            return False, "Input not found — not logged in"
        except Exception as e:
            return False, str(e)
        finally:
            page.close()

    def _check_gemini_session(self, page) -> Tuple[bool, str]:
        """
        Verificación de sesión específica para Gemini.
        Gemini muestra un textarea incluso sin login (landing pública).
        Hay que verificar que el usuario esté autenticado viendo si aparece
        la interfaz de chat completa (no la landing de marketing).
        """
        page.wait_for_timeout(3000)

        current_url = page.url
        log.debug(f"[gemini] Session check URL: {current_url}")

        # Si redirige a accounts.google.com, no autenticado
        if "accounts.google.com" in current_url or "signin" in current_url:
            return False, f"Redirigido a login de Google: {current_url}"

        # Verificar que la página cargó correctamente
        content_check = page.evaluate("""() => {
            const body = document.body ? document.body.innerText : '';
            const isLanding = body.includes('Supercharge your creativity') ||
                              body.includes('Superpotencia tu creatividad') ||
                              body.includes('Get more done') ||
                              (body.includes('Sign in') && !body.includes('Sign out'));
            const hasChat = document.querySelector(
                'rich-textarea, div[contenteditable="true"], textarea[placeholder*="Gemini"],' +
                ' .ql-editor, bard-input-footer'
            ) !== null;
            const isLoggedIn = document.querySelector(
                '.gb_A, [aria-label*="Google Account"], [data-gbid="gb_A"], ' +
                'wayfinder-nav-item, gmat-toolbar'
            ) !== null;
            return { isLanding, hasChat, isLoggedIn };
        }""")

        log.debug(f"[gemini] Session check result: {content_check}")

        if content_check.get("isLoggedIn"):
            return True, "OK - usuario autenticado en Google"

        if content_check.get("hasChat") and not content_check.get("isLanding"):
            return True, "OK - interfaz de chat disponible"

        if content_check.get("isLanding"):
            return False, "Página de marketing de Gemini — no autenticado"

        # Si tiene el input y no es landing, probablemente OK
        input_selectors = self._get_input_selectors()
        for sel in input_selectors:
            try:
                page.wait_for_selector(sel, timeout=5000)
                return True, "OK"
            except:
                continue

        return False, "No se encontró interfaz de chat de Gemini"

    def _check_meta_session(self, page) -> Tuple[bool, str]:
        """
        Verificación de sesión específica para Meta AI.
        Meta muestra input incluso en modo invitado, así que
        verificamos que haya señales reales de sesión autenticada.
        """
        page.wait_for_timeout(3000)

        current_url = page.url
        log.debug(f"[meta] Session check URL: {current_url}")

        # Verificar primero si las cookies incluyen c_user (señal de sesión Facebook)
        has_session_cookie = False
        try:
            cookies = page.context.cookies()
            cookie_names = [c["name"] for c in cookies]
            has_session_cookie = "c_user" in cookie_names or "xs" in cookie_names
            log.debug(f"[meta] Cookies en contexto: {cookie_names[:10]}... c_user={'c_user' in cookie_names}, xs={'xs' in cookie_names}")
        except Exception as e:
            log.debug(f"[meta] Could not check cookies: {e}")

        content_check = page.evaluate("""() => {
            const body = document.body ? document.body.innerText : '';
            const isLoginPage = body.includes('Log in') && body.includes('Sign up') &&
                                !body.includes('Log out');
            const hasInput = document.querySelector(
                'div[contenteditable="true"][role="textbox"], textarea[placeholder*="Ask"], ' +
                'div[data-testid="chat-input"]'
            ) !== null;
            // Detectar si hay avatar/menu de usuario autenticado
            const hasUserMenu = document.querySelector(
                '[data-testid="user-menu"], [aria-label*="Account"], [aria-label*="Cuenta"], ' +
                'img[alt*="profile" i], [data-testid="mwthreadlist"]'
            ) !== null;
            // Detectar conversaciones previas (señal de sesión real)
            const hasConversations = document.querySelectorAll(
                '[data-testid*="conversation"], [class*="ConversationItem"], ' +
                'a[href*="/c/"]'
            ).length > 0;
            return { isLoginPage, hasInput, hasUserMenu, hasConversations };
        }""")

        log.debug(f"[meta] Session check result: {content_check}")

        if content_check.get("isLoginPage"):
            return False, "Página de login de Meta — no autenticado"

        # Meta muestra input en modo invitado, no es suficiente
        if not has_session_cookie:
            if content_check.get("hasInput"):
                return False, "Meta AI en modo invitado — faltan cookies de sesión (c_user, xs). Copia cookies desde facebook.com"
            return False, "No autenticado en Meta AI — faltan cookies de Facebook (c_user, xs)"

        if content_check.get("hasInput"):
            return True, "OK — sesión autenticada"

        # Fallback: buscar input
        input_selectors = self._get_input_selectors()
        for sel in input_selectors:
            try:
                page.wait_for_selector(sel, timeout=8000)
                return True, "OK"
            except:
                continue

        return False, "No se encontró interfaz de chat de Meta AI"

    # ════════════════════════════════════════════════════════
    #  MAIN SEND METHOD
    # ════════════════════════════════════════════════════════
    def send_prompt(self, prompt: str, keep_page: bool = False) -> str:
        """
        Envía un prompt al chat y devuelve la respuesta.

        keep_page=False (por defecto): abre tab nueva, cierra al terminar (modo limpio)
        keep_page=True:  reutiliza self.page si ya existe (modo conversación continua —
                         escribe en el input de la misma página sin recargar)
        """
        log.info("="*50)
        log.info(f"[{self.model_name}] SEND PROMPT (keep_page={keep_page})")
        log.info("="*50)

        if not self._browser:
            self.start()

        # ── Pre-check: Meta necesita cookies de Facebook ──────
        if self.model_name == "meta" and self._cookies:
            cookie_names = list(self._cookies.keys()) if isinstance(self._cookies, dict) else [c.get("name","") for c in self._cookies]
            if "c_user" not in cookie_names and "xs" not in cookie_names:
                log.error(f"[meta] Cookies insuficientes: faltan c_user y xs. Tienes: {cookie_names[:8]}")
                log.error(f"[meta] Necesitas copiar cookies desde facebook.com (logueado), no desde meta.ai")
                raise RuntimeError("Cookies de Meta incompletas — falta c_user/xs de facebook.com. Copia cookies desde Cookie-Editor en facebook.com")

        # ── Modo conversación continua ─────────────────────────
        # Si keep_page=True y ya tenemos una página abierta, no navegamos de nuevo.
        # Solo escribimos en el input existente.
        nueva_tab = False
        if keep_page and self.page and not self.page.is_closed():
            log.info(f"[{self.model_name}] Reusing existing page (conversación continua)")
        else:
            # Abrir tab nueva (comportamiento estándar)
            self.page = self._ctx.new_page()
            nueva_tab = True
            log.info(f"[{self.model_name}] New tab created")

        # Para Meta AI: limpiar chunks antes de cualquier prompt
        if self.model_name == "meta":
            with self._meta_response_lock:
                self._meta_response_chunks = []

        try:
            if nueva_tab:
                # Solo navegamos si abrimos tab nueva
                self._navigate()

                # Para Meta AI: configurar intercept UNA sola vez después de navegar
                if self.model_name == "meta":
                    self._setup_meta_network_intercept()

            # Escribir prompt
            if not self._type_prompt(prompt):
                raise RuntimeError("Could not type prompt — no input found")

            # Enviar
            self._click_submit()

            # Esperar respuesta
            self._wait_for_response()

            # Extraer respuesta
            response = self._extract_response()

            if response:
                log.info("="*50)
                log.info(f"[{self.model_name}] RESPONSE: {len(response)} chars")
                log.info("="*50)
            else:
                log.warning(f"[{self.model_name}] Empty response")

            return response
        finally:
            # En modo keep_page dejamos la página abierta para el siguiente mensaje.
            # En modo normal cerramos siempre.
            if not keep_page:
                if self.page and not self.page.is_closed():
                    self.page.close()
                    self.page = None
                    log.info(f"[{self.model_name}] Tab closed")


# ════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="ANTI-API - Chat IA via Playwright")
    parser.add_argument("--url", required=True, help="URL del chat")
    parser.add_argument("--model", default="generic", choices=["grok", "gemini", "meta", "generic"])
    parser.add_argument("--cookies", help="JSON de cookies (archivo o string)")
    parser.add_argument("--prompt", default="Hola", help="Prompt a enviar")
    parser.add_argument("--headless", action="store_true", help="Sin ventana visible")

    args = parser.parse_args()

    cookies = {}
    if args.cookies:
        if os.path.isfile(args.cookies):
            with open(args.cookies, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(args.cookies)
        cookies = normalize_cookies(data)

    chat = AntiApiChat(
        url=args.url,
        model_name=args.model,
        headless=args.headless,
        cookies=cookies,
    )

    try:
        response = chat.send_prompt(args.prompt)
        print(response)
    except Exception as e:
        log.error(f"Error: {e}")
        import traceback
        log.debug(traceback.format_exc())
        raise
    finally:
        chat.close()


if __name__ == "__main__":
    main()
