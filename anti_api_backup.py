"""
ANTI-API - Sistema de automatización de chats de IA
Basado en el sistema de Grok (IVAN-VIDEO-NEW!!!!!!)
Soporta cookies en formato simple JSON clave-valor
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Union

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

# Configurar logging para ver en CMD
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("AntiAPI")


# Configuración de cookies por modelo (nombre de cookies esperadas y dominios)
MODEL_COOKIE_CONFIG = {
    "grok": {
        "required_cookies": ["sso", "sso-rw", "x-userid"],
        "optional_cookies": ["i18nextLng"],
        "domains": [".grok.com", ".x.ai"],
        "url": "https://grok.com",
    },
    "gemini": {
        "required_cookies": ["__Secure-1PSID", "__Secure-1PSIDTS"],
        "optional_cookies": ["__Secure-1PAPISID", "__Secure-3PSID", "NID"],
        "domains": [".google.com", ".gemini.google.com"],
        "url": "https://gemini.google.com",
    },
    "meta": {
        "required_cookies": [],  # Meta usa todas las cookies disponibles
        "optional_cookies": ["c_user", "xs", "datr", "fr", "sb", "presence"],
        "domains": [".meta.ai"],
        "url": "https://www.meta.ai",
    },
}


def random_sleep(min_seconds: float = 0.3, max_seconds: float = 1.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def normalize_cookies(cookie_input: Union[Dict, List]) -> Dict[str, str]:
    """
    Normaliza cookies de diferentes formatos a dict simple clave-valor.
    Soporta:
    - Dict simple: {"name": "value", ...}
    - List de objetos cookie: [{"name": "x", "value": "y"}, ...]
    """
    if isinstance(cookie_input, dict):
        # Ya es un dict, verificar si tiene formato de cookie de navegador
        if all(isinstance(v, str) for v in cookie_input.values()):
            return cookie_input
        # Si tiene estructura de cookie con 'name' y 'value'
        result = {}
        for k, v in cookie_input.items():
            if isinstance(v, str):
                result[k] = v
        return result

    elif isinstance(cookie_input, list):
        # Formato array de cookies del navegador
        result = {}
        for item in cookie_input:
            if isinstance(item, dict) and "name" in item and "value" in item:
                result[item["name"]] = item["value"]
        return result

    return {}


class AntiApiChat:
    """
    Cliente de chat usando Playwright.
    Soporta cookies en formato simple dict (estilo Grok system).
    """

    def __init__(
        self,
        url: str,
        model_name: str = "generic",
        headless: bool = True,  # Default True como Grok - sin abrir navegador visible
        cookies: Optional[Dict[str, str]] = None,
        input_selector: Optional[str] = None,
        timeout: int = 60,
        validate_session: bool = False,  # False = puentear validación, usar cookies directamente
    ):
        self.url = url
        self.model_name = model_name.lower()
        self.headless = headless
        self.cookies = cookies or {}
        self.input_selector = input_selector
        self.timeout = timeout
        self.validate_session = validate_session

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _build_cookie_list(self) -> List[Dict[str, Any]]:
        """
        Construye lista de cookies para Playwright a partir del dict simple.
        EXACTAMENTE como Grok: solo name, value, domain, path.
        """
        cookie_list = []

        # Obtener configuración del modelo
        config = MODEL_COOKIE_CONFIG.get(self.model_name, {})
        domains = config.get("domains", ["." + self.url.split("/")[2].replace("www.", "")])
        required = config.get("required_cookies", [])
        optional = config.get("optional_cookies", [])
        
        # Solo procesar cookies requeridas + opcionales (como Grok)
        important_cookies = list(set(required + optional))
        
        # Si no hay configuración específica, usar las cookies que parecen de sesión
        if not important_cookies:
            session_patterns = ["session", "auth", "token", "ssid", "sid", "login", 
                               "secure", "psid", "apisid", "hsid", "c_user", "xs", "sso"]
            important_cookies = [name for name in self.cookies.keys() 
                                if any(p.lower() in name.lower() for p in session_patterns)]
            log.debug(f"   Cookies de sesión detectadas: {important_cookies}")

        # Construir cookies EXACTAMENTE como Grok (solo 4 campos)
        # Solo usar el primer dominio para evitar duplicados
        primary_domain = domains[0] if domains else "." + self.url.split("/")[2].replace("www.", "")
        
        for name in important_cookies:
            val = self.cookies.get(name)
            if val:
                cookie_list.append({
                    "name": name,
                    "value": str(val),
                    "domain": primary_domain,
                    "path": "/"
                })

        # Si no hay cookies importantes, usar todas las disponibles (fallback)
        if not cookie_list:
            log.warning("⚠️ No se encontraron cookies importantes, usando todas las disponibles")
            for name, val in self.cookies.items():
                cookie_list.append({
                    "name": name,
                    "value": str(val),
                    "domain": primary_domain,
                    "path": "/"
                })

        if not cookie_list:
            raise ValueError("No hay cookies disponibles para inyectar")

        log.debug(f"   Cookies a inyectar: {len(cookie_list)}")
        return cookie_list

    def start(self) -> None:
        """Inicia el navegador y carga las cookies."""
        log.info(f"🚀 Iniciando navegador (headless={self.headless})")
        log.debug(f"   URL objetivo: {self.url}")
        log.debug(f"   Modelo: {self.model_name}")
        
        self.playwright = sync_playwright().start()
        log.debug("   Playwright iniciado")

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--disable-default-apps",
            "--window-size=1280,800",
        ]

        try:
            log.debug("   Lanzando Chrome...")
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=launch_args,
            )
            log.info("✅ Navegador iniciado correctamente")
        except Exception as e:
            log.error(f"❌ Error al iniciar navegador: {e}")
            self.playwright.stop()
            if "executable" in str(e).lower():
                raise RuntimeError("Chrome no instalado. Descarga desde google.com/chrome")
            raise

        log.debug("   Creando contexto del navegador...")
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        log.debug("   Contexto creado")

        # Inyectar cookies si existen
        if self.cookies:
            log.info(f"📦 Cookies disponibles: {len(self.cookies)}")
            cookie_list = self._build_cookie_list()
            if cookie_list:
                cookie_names = list(set(c["name"] for c in cookie_list))
                log.info(f"🍪 Inyectando {len(cookie_list)} cookies ({len(cookie_names)} únicas): {', '.join(cookie_names[:5])}")
                try:
                    self.context.add_cookies(cookie_list)
                    log.info(f"✅ Cookies inyectadas correctamente")
                except Exception as e:
                    log.error(f"❌ Error inyectando cookies: {e}")
                    log.debug(f"   Cookies que fallaron: {cookie_list[:2]}")  # Mostrar ejemplos
            else:
                config = MODEL_COOKIE_CONFIG.get(self.model_name, {})
                required = config.get("required_cookies", [])
                if required:
                    raise ValueError(f"No se encontraron cookies requeridas: {', '.join(required)}")
                else:
                    log.warning("⚠️ No se pudieron construir cookies para inyectar")
        else:
            log.warning("⚠️ No hay cookies proporcionadas")

        log.debug("   Abriendo nueva página...")
        self.page = self.context.new_page()
        log.info("✅ Página lista")

    def validate_session(self) -> tuple[bool, str]:
        """Verifica que la sesión esté activa navegando al sitio."""
        log.info(f"🌐 Navegando a: {self.url}")
        try:
            log.debug("   Cargando página (timeout 45s)...")
            self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
            log.debug("   Página cargada, esperando 3s...")
            time.sleep(3)

            url = self.page.url
            log.info(f"📍 URL actual: {url}")

            # Detectar redirecciones a login
            login_indicators = ["login", "auth", "signin", "/i/flow"]
            if any(x in url.lower() for x in login_indicators):
                log.error(f"❌ Redirigido a login: {url}")
                return False, f"Redirigido a login: {url}"
            
            # Detectar página de consentimiento de Google
            if "consent.google.com" in url.lower():
                log.warning("⚠️ Detectada página de consentimiento de Google")
                log.info("   Intentando aceptar automáticamente...")
                try:
                    # Intentar clic en botón de aceptar/rechazar todo
                    for btn_text in ["Reject all", "Rechazar todo", "Accept all", "Aceptar todo", "Manage", "Gestionar"]:
                        try:
                            btn = self.page.locator(f'button:has-text("{btn_text}")').first
                            if btn.count() > 0 and btn.is_visible():
                                log.info(f"   Clic en: {btn_text}")
                                btn.click()
                                self.page.wait_for_timeout(2000)
                                break
                        except:
                            continue
                    # Esperar redirección
                    self.page.wait_for_timeout(3000)
                    new_url = self.page.url
                    if "consent.google.com" not in new_url.lower():
                        log.info("✅ Consentimiento gestionado, redirigiendo...")
                        return self.validate_session()  # Revalidar
                except Exception as e:
                    log.error(f"   Error gestionando consentimiento: {e}")

            # Buscar campo de entrada para confirmar que estamos logueados
            input_selectors = [
                self.input_selector,
                'div[contenteditable="true"]',
                "textarea",
                "input[type='text']",
                '[role="textbox"]',
            ]

            log.debug("   Buscando campo de entrada...")
            for sel in input_selectors:
                if not sel:
                    continue
                try:
                    self.page.wait_for_selector(sel, timeout=10000)
                    log.info(f"✅ Campo de entrada encontrado: {sel}")
                    return True, "OK"
                except:
                    log.debug(f"   Selector no encontrado: {sel}")
                    continue

            log.error("❌ No se encontró campo de entrada")
            return False, "No se encontró campo de entrada - posiblemente no logueado"

        except Exception as e:
            log.error(f"❌ Error durante validación: {e}")
            import traceback
            log.debug(traceback.format_exc())
            return False, str(e)

    def _find_input(self):
        """Encuentra el campo de entrada del chat."""
        log.debug("🔍 Buscando campo de entrada...")
        selectors = []
        if self.input_selector:
            selectors.append(self.input_selector)
            log.debug(f"   Selector personalizado: {self.input_selector}")

        # Selectores específicos por modelo
        model_selectors = {
            "grok": [
                'div.ProseMirror[contenteditable="true"]',
                'div[contenteditable="true"]',
            ],
            "gemini": [
                'div[contenteditable="true"]',
                'textarea',
                'div[role="textbox"]',
            ],
            "meta": [
                'div[contenteditable="true"]',
                'textarea',
                'input[type="text"]',
            ],
        }

        selectors.extend(model_selectors.get(self.model_name, []))
        selectors.extend([
            "textarea",
            'div[contenteditable="true"]',
            "input[type='text']",
            '[role="textbox"]',
        ])

        for selector in selectors:
            log.debug(f"   Probando selector: {selector}")
            locator = self.page.locator(selector)
            count = locator.count()
            if count > 0:
                log.info(f"✅ Campo de entrada encontrado: {selector}")
                return locator.first
            log.debug(f"   No encontrado (count={count})")

        log.error(f"❌ No se encontró ningún campo de entrada. Selectores probados: {len(selectors)}")
        raise RuntimeError("No se encontró el campo de entrada del chat.")

    def _type_human(self, element, text: str) -> None:
        """Escribe texto simulando comportamiento humano."""
        log.info(f"⌨️  Escribiendo prompt ({len(text)} caracteres)...")
        element.click()
        time.sleep(0.3)

        # Limpiar campo primero
        log.debug("   Limpiando campo...")
        self.page.keyboard.press("Control+a")
        time.sleep(0.1)
        self.page.keyboard.press("Backspace")
        time.sleep(0.2)

        # Escribir con delays aleatorios
        log.debug("   Escribiendo texto...")
        for i, char in enumerate(text):
            element.type(char, delay=random.randint(30, 80))
            if i % 20 == 0 and i > 0:
                log.debug(f"   Progreso: {i}/{len(text)} caracteres")

        random_sleep(0.5, 1.0)
        log.debug("   Texto escrito")

    def _click_submit(self) -> bool:
        """Hace clic en el botón de enviar."""
        log.debug("🔘 Buscando botón de enviar...")
        time.sleep(1)

        submit_selectors = {
            "grok": [
                'button[type="submit"]',
                'button[aria-label*="send" i]',
            ],
            "gemini": [
                'button[aria-label="Enviar"]',
                'button[aria-label="Send"]',
                'button:has-text("Enviar")',
                'button.send-button',
                'button[type="submit"]',
            ],
            "meta": [
                'button[type="submit"]',
                'button[aria-label="Send"]',
                'button[aria-label*="Enviar" i]',
            ],
        }

        selectors = submit_selectors.get(self.model_name, [])
        selectors.extend([
            'button[type="submit"]',
            'button[aria-label*="send" i]',
            'button:has-text("Enviar")',
            'button:has-text("Send")',
        ])

        for selector in selectors:
            try:
                log.debug(f"   Probando botón: {selector}")
                btn = self.page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    log.info(f"✅ Botón encontrado, haciendo clic: {selector}")
                    btn.click(force=True, timeout=3000)
                    log.info("✅ Click realizado")
                    return True
            except Exception as e:
                log.debug(f"   Error con selector {selector}: {e}")
                continue

        # Fallback: enviar con Enter
        log.warning("⚠️ No se encontró botón, usando Enter como fallback")
        try:
            self.page.keyboard.press("Enter")
            log.info("✅ Enviado con Enter")
            return True
        except Exception as e:
            log.error(f"❌ Error al presionar Enter: {e}")
            pass

        return False

    def _wait_for_response(self) -> None:
        """Espera a que termine de generar la respuesta."""
        log.info("⏳ Esperando que se genere la respuesta...")
        log.debug(f"   Modelo: {self.model_name}")
        # Indicadores de carga por modelo
        loading_selectors = {
            "grok": [
                ".animate-spin",
                '[data-testid="loading"]',
                ".loading-indicator",
            ],
            "gemini": [
                ".loading-indicator",
                'div[aria-busy="true"]',
                ".skeleton",
                'svg[aria-label="Cargando"]',
            ],
            "meta": [
                '[aria-label="Generating"]',
                ".loading-spinner",
                ".animate-spin",
            ],
        }

        selectors = loading_selectors.get(self.model_name, [])
        selectors.extend([
            ".animate-spin",
            ".loading",
            '[data-testid="loading"]',
        ])

        # Esperar a que desaparezcan los indicadores de carga
        log.debug(f"   Probando {len(selectors)} selectores de carga...")
        for selector in selectors:
            try:
                log.debug(f"   Esperando que desaparezca: {selector}")
                self.page.wait_for_selector(
                    selector,
                    state="detached",
                    timeout=60000
                )
                log.info("✅ Respuesta lista (indicador desapareció)")
                return
            except PlaywrightTimeoutError:
                log.debug(f"   Timeout esperando: {selector}")
                continue

        log.warning("⚠️ No se detectaron indicadores de carga, esperando tiempo fijo...")
        time.sleep(10)

    def _extract_last_response(self) -> str:
        """Extrae la última respuesta del asistente usando JavaScript."""
        log.debug("📤 Extrayendo respuesta...")
        
        # Script JavaScript para encontrar el último mensaje del asistente
        extract_script = """
        () => {
            // Palabras a filtrar (UI, disclaimers, etc)
            const filterWords = [
                'Enviar', 'Send', 'micrófono', 'Nueva conversación', 
                'Ajustes', 'Settings', 'Gemini no es humano',
                'puede cometer errores', 'verifica sus respuestas',
                'Tu privacidad', 'Se abre en una ventana nueva',
                'Mostrar menú', 'Editar petición', 'Detener respuesta',
                'Usar micrófono'
            ];
            
            // Buscar mensajes por atributos comunes
            const selectors = [
                '[data-message-author-role="assistant"]',
                '[data-testid="conversation-turn-response"]',
                '[data-testid="assistant-message"]',
                'div[class*="assistant"]',
                'div[class*="message"][class*="assistant"]',
                '.markdown',
                '.prose',
                'div.message-content',
                'div[data-testid="conversation-turn"]'
            ];
            
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    // Obtener el último elemento
                    const last = elements[elements.length - 1];
                    const text = last.innerText || last.textContent;
                    if (text && text.trim().length > 20) {
                        const trimmed = text.trim();
                        // Verificar que no sea solo UI
                        const hasFilterWord = filterWords.some(w => trimmed.toLowerCase().includes(w.toLowerCase()));
                        if (!hasFilterWord || trimmed.length > 200) {
                            return trimmed;
                        }
                    }
                }
            }
            
            // Fallback: buscar en todos los divs con texto largo
            const allDivs = document.querySelectorAll('div');
            for (let i = allDivs.length - 1; i >= 0; i--) {
                const div = allDivs[i];
                const text = div.innerText || div.textContent;
                if (text && text.trim().length > 100) {
                    const trimmed = text.trim();
                    const hasFilterWord = filterWords.some(w => trimmed.toLowerCase().includes(w.toLowerCase()));
                    if (!hasFilterWord) {
                        return trimmed;
                    }
                }
            }
            
            return '';
        }
        """
        
        try:
            response = self.page.evaluate(extract_script)
            if response and len(response) > 20:
                log.info(f"✅ Respuesta encontrada ({len(response)} chars)")
                log.debug(f"   Preview: {response[:100]}...")
                return response
        except Exception as e:
            log.debug(f"   Error en extracción JS: {e}")

        log.error("❌ No se pudo extraer ninguna respuesta")
        return ""

    def send_prompt(self, prompt: str) -> str:
        """
        Envía un prompt al chat y devuelve la respuesta.
        """
        log.info("="*50)
        log.info("🚀 INICIANDO ENVÍO DE PROMPT")
        log.info("="*50)
        
        if not self.browser:
            self.start()

        # Validar sesión solo si está habilitado
        if self.validate_session:
            valid, msg = self.validate_session()
            if not valid:
                log.error(f"❌ Validación fallida: {msg}")
                raise RuntimeError(f"Sesión inválida: {msg}")
            log.info("✅ Sesión validada")
        else:
            log.info("⏭️  Validación deshabilitada, usando cookies directamente")
            # Navegar a la URL para cargar la página con las cookies
            log.info(f"🌐 Navegando a: {self.url}")
            self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)

        log.info(f"📤 Prompt: {prompt[:80]}...")

        # Encontrar y usar campo de entrada
        input_element = self._find_input()
        self._type_human(input_element, prompt)

        # Enviar
        if not self._click_submit():
            log.warning("⚠️ Usando fallback Enter")
            self.page.keyboard.press("Enter")

        # Esperar respuesta
        self._wait_for_response()

        # Extraer respuesta
        response = self._extract_last_response()

        if response:
            log.info("="*50)
            log.info(f"✅ RESPUESTA RECIBIDA: {len(response)} caracteres")
            log.info("="*50)
            log.debug(f"Preview: {response[:200]}...")
        else:
            log.warning("⚠️ Respuesta vacía")

        return response

    def close(self) -> None:
        """Cierra el navegador y libera recursos."""
        log.info("🔒 Cerrando navegador...")
        try:
            if self.context:
                self.context.close()
                log.debug("   Contexto cerrado")
        except Exception as e:
            log.debug(f"   Error cerrando contexto: {e}")
        try:
            if self.browser:
                self.browser.close()
                log.debug("   Navegador cerrado")
        except Exception as e:
            log.debug(f"   Error cerrando navegador: {e}")
        try:
            if self.playwright:
                self.playwright.stop()
                log.debug("   Playwright detenido")
        except Exception as e:
            log.debug(f"   Error deteniendo playwright: {e}")

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        log.info("✅ Recursos liberados")


def main():
    log.info("🔧 ANTI-API CLI iniciado")
    parser = argparse.ArgumentParser(
        description="ANTI-API - Interactuar con chats de IA via Playwright"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL del chat (ej: https://gemini.google.com)",
    )
    parser.add_argument(
        "--model",
        default="generic",
        choices=["grok", "gemini", "chatgpt", "meta", "generic"],
        help="Modelo a usar (para selectores específicos)",
    )
    parser.add_argument(
        "--cookies",
        help="JSON de cookies simple (archivo o string). Ej: '{\"ssid\":\"xxx\"}'",
    )
    parser.add_argument(
        "--prompt",
        default="Hola",
        help="Prompt a enviar",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar sin ventana visible",
    )
    parser.add_argument(
        "--selector",
        help="Selector CSS del campo de entrada (opcional, usa por defecto del modelo)",
    )

    args = parser.parse_args()

    # Cargar cookies
    cookies = {}
    if args.cookies:
        if os.path.isfile(args.cookies):
            with open(args.cookies, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(args.cookies)
        cookies = normalize_cookies(data)

    log.info("="*50)
    log.info("CONFIGURACIÓN")
    log.info("="*50)
    log.info(f"   Modelo: {args.model}")
    log.info(f"   URL: {args.url}")
    log.info(f"   Cookies: {len(cookies)} encontradas")
    if cookies:
        log.info(f"   Nombres: {', '.join(cookies.keys())}")

    chat = AntiApiChat(
        url=args.url,
        model_name=args.model,
        headless=args.headless,
        cookies=cookies,
        input_selector=args.selector,
    )

    try:
        response = chat.send_prompt(args.prompt)
        log.info("\n" + "=" * 50)
        log.info("RESPUESTA FINAL:")
        log.info("=" * 50)
        print(response)  # Sin prefijo de log para que sea limpio
        log.info("=" * 50)
    except Exception as e:
        log.error(f"\n❌ Error: {e}")
        import traceback
        log.debug(traceback.format_exc())
        raise
    finally:
        chat.close()


if __name__ == "__main__":
    main()
