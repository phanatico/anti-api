"""
ANTI-API - Async Version (Playwright async para paralelismo)
Basado en el sistema de videos Grok (grok_playwright_source.py)
Soporta múltiples prompts concurrentes con semáforo.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

# Configuración de cookies por modelo
MODEL_COOKIE_CONFIG = {
    "grok": {
        "required_cookies": ["sso", "sso-rw", "x-userid"],
        "optional_cookies": ["i18nextLng"],
        "domains": [".grok.com", ".x.ai"],
        "url": "https://grok.com/",
    },
    "gemini": {
        "required_cookies": ["__Secure-1PSID", "__Secure-1PSIDTS"],
        "optional_cookies": ["SID", "HSID", "SSID", "APISID", "SAPISID"],
        "domains": [".google.com"],
        "url": "https://gemini.google.com/",
    },
    "meta": {
        "required_cookies": [],  # Meta usa todas las cookies disponibles
        "optional_cookies": ["c_user", "xs", "datr", "fr", "sb", "presence"],
        "domains": [".meta.ai"],
        "url": "https://www.meta.ai",
    },
}


def _sanitize_cookie_value(val: str) -> str:
    """Sanitiza valor de cookie para evitar errores de Playwright."""
    if not val:
        return ""
    # Eliminar caracteres problemáticos
    val = str(val).strip()
    # Truncar si es muy largo (Playwright limita a ~4096)
    if len(val) > 4096:
        val = val[:4096]
    return val


def normalize_cookies(cookie_input: Union[Dict, List]) -> Dict[str, str]:
    """Normaliza cookies a dict simple clave-valor."""
    if isinstance(cookie_input, dict):
        if all(isinstance(v, str) for v in cookie_input.values()):
            return cookie_input
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


class AntiApiChatAsync:
    """
    Cliente de chat usando Playwright ASYNC.
    Soporta múltiples prompts concurrentes con semáforo.
    
    Uso:
        chat = AntiApiChatAsync(url="https://grok.com/", model_name="grok", cookies=cookies)
        await chat.start(max_tabs=10)  # Máximo 10 tabs en paralelo
        response = await chat.send_prompt("Hola")
        await chat.stop()
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
        self._sem = None  # Semaphore para limitar concurrencia
        self._started = False

    # ════════════════════════════════════════════════════════
    #  LIFECYCLE (async, como GrokConverter)
    # ════════════════════════════════════════════════════════
    async def start(self, max_tabs: int = 10):
        """Inicia el navegador e inyecta cookies. Idéntico a GrokConverter.start()"""
        if self._started:
            log.info(f"[{self.model_name}] Browser already started, reusing...")
            return

        log.info(f"[{self.model_name}] Starting browser (headless={self.headless}, max_tabs={max_tabs})...")

        self._pw = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--incognito",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--disable-default-apps",
            "--window-size=1280,800",
            "--window-position=0,0",
        ]

        try:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=launch_args,
            )
        except Exception as e:
            await self._pw.stop()
            if "executable" in str(e).lower() or "not found" in str(e).lower():
                raise RuntimeError("Chrome no instalado. Descarga desde google.com/chrome")
            raise

        self._ctx = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # Inyectar cookies
        await self._inject_cookies()

        # Semáforo para limitar concurrencia
        self._sem = asyncio.Semaphore(max_tabs)

        self._started = True
        log.info(f"[{self.model_name}] Browser ready (max {max_tabs} parallel tabs)")

    async def _inject_cookies(self) -> None:
        """Inyecta cookies en TODOS los dominios configurados."""
        if not self.cookies:
            log.warning(f"[{self.model_name}] No cookies provided")
            return

        config = MODEL_COOKIE_CONFIG.get(self.model_name, {})
        domains = config.get("domains", ["." + self.url.split("/")[2].replace("www.", "")])

        all_cookie_names = list(self.cookies.keys())
        log.debug(f"[{self.model_name}] Cookies disponibles: {all_cookie_names}")

        cookie_list = []
        for name in all_cookie_names:
            val = self.cookies.get(name)
            if val:
                val = _sanitize_cookie_value(str(val))
                if not val:
                    continue
                for domain in domains:
                    cookie_list.append({
                        "name": name,
                        "value": val,
                        "domain": domain,
                        "path": "/"
                    })

        if not cookie_list:
            raise ValueError(f"No valid cookies to inject. Available: {list(self.cookies.keys())}")

        try:
            await self._ctx.add_cookies(cookie_list)
            unique_names = list(set(c["name"] for c in cookie_list))
            log.info(f"[{self.model_name}] {len(cookie_list)} cookies injected "
                     f"({len(unique_names)} unique): {', '.join(unique_names)}")
        except Exception as e:
            log.error(f"[{self.model_name}] Cookie injection failed: {e}")
            success_count = 0
            for c in cookie_list:
                try:
                    await self._ctx.add_cookies([c])
                    success_count += 1
                except Exception as ce:
                    log.warning(f"   Cookie '{c['name']}' failed: {ce}")
            log.info(f"[{self.model_name}] Partial injection: {success_count}/{len(cookie_list)} cookies")

    async def stop(self):
        """Cierra navegador y libera recursos."""
        try:
            if self._ctx: await self._ctx.close()
            if self._browser: await self._browser.close()
            if self._pw: await self._pw.stop()
        except:
            pass
        self._ctx = self._browser = self._pw = None
        self._started = False
        log.info(f"[{self.model_name}] Browser closed")

    # ════════════════════════════════════════════════════════
    #  SELECTORS
    # ════════════════════════════════════════════════════════
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
                'div[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"]',
                'textarea',
            ],
            "meta": [
                'div[contenteditable="true"][role="textbox"]',
                'div[data-testid="chat-input"]',
                'div[contenteditable="true"]',
                'textarea',
            ],
        }
        model_selectors = selectors.get(self.model_name, ["div[contenteditable='true']", "textarea"])
        if self.input_selector:
            model_selectors.insert(0, self.input_selector)
        return model_selectors

    # ════════════════════════════════════════════════════════
    #  MAIN SEND METHOD (async con semáforo)
    # ════════════════════════════════════════════════════════
    async def send_prompt(self, prompt: str) -> str:
        """
        Envía un prompt al chat y devuelve la respuesta.
        Usa semáforo para limitar concurrencia.
        """
        log.info("="*50)
        log.info(f"[{self.model_name}] SEND PROMPT")
        log.info("="*50)

        if not self._browser:
            await self.start()

        # Adquirir semáforo (limita concurrencia)
        async with self._sem:
            page = await self._ctx.new_page()
            log.info(f"[{self.model_name}] New tab created (semaphore acquired)")

            try:
                # Navegar
                await self._navigate(page)

                # Escribir prompt
                if not await self._type_prompt(page, prompt):
                    raise RuntimeError("Could not type prompt — no input found")

                # Enviar
                await self._click_submit(page)

                # Esperar respuesta
                await self._wait_for_response(page)

                # Extraer respuesta
                response = await self._extract_response(page)

                if response:
                    log.info("="*50)
                    log.info(f"[{self.model_name}] RESPONSE: {len(response)} chars")
                    log.info("="*50)
                else:
                    log.warning(f"[{self.model_name}] Empty response")

                return response
            finally:
                await page.close()
                log.info(f"[{self.model_name}] Tab closed (semaphore released)")

    # ════════════════════════════════════════════════════════
    #  NAVIGATE
    # ════════════════════════════════════════════════════════
    async def _navigate(self, page) -> None:
        """Navega a la URL y espera que el input esté listo."""
        log.info(f"[{self.model_name}] Navigating to {self.url}...")
        
        selectors = self._get_input_selectors()
        
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            
            # Verificar login
            content = await page.content()
            if any(x in content.lower() for x in ["login", "auth", "signin", "/i/flow"]):
                log.error(f"[{self.model_name}] ❌ PÁGINA DE LOGIN DETECTADA")
                raise RuntimeError("Cookies inválidas - página muestra login")
            
            # Encontrar input
            for sel in selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                    log.info(f"[{self.model_name}] Page ready (input found: {sel})")
                    return
                except:
                    continue
            
            log.error(f"[{self.model_name}] Input not found after 5s")
            raise RuntimeError("Input not found")
            
        except Exception as e:
            if "login" in str(e).lower():
                raise RuntimeError("Cookies inválidas - página muestra login")
            raise

    # ════════════════════════════════════════════════════════
    #  TYPE PROMPT
    # ════════════════════════════════════════════════════════
    async def _type_prompt(self, page, prompt: str) -> bool:
        """Escribe el prompt usando JavaScript directo."""
        selectors = self._get_input_selectors()
        log.info(f"[{self.model_name}] Typing prompt...")
        
        js_result = await page.evaluate("""
            ({selectors, text}) => {
                for (const sel of selectors) {
                    try {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const rect = el.getBoundingClientRect();
                            const isVisible = rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight;
                            const isEnabled = !el.disabled && !el.getAttribute('disabled');
                            
                            if (isVisible && isEnabled) {
                                el.focus();
                                el.click();
                                
                                if (el.contentEditable === 'true') {
                                    el.innerHTML = '';
                                    const textNode = document.createTextNode(text);
                                    el.appendChild(textNode);
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    return { success: true, method: 'contenteditable', selector: sel };
                                }
                                
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
            log.info(f"[{self.model_name}] Prompt typed via JS ({js_result.get('method')})")
            await page.wait_for_timeout(500)
            return True
        
        # Fallback con keyboard
        log.debug(f"[{self.model_name}] JS method failed, trying keyboard...")
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.scroll_into_view_if_needed()
                    await el.click(force=True, timeout=3000)
                    await page.wait_for_timeout(300)
                    
                    await page.keyboard.press("Control+a")
                    await page.wait_for_timeout(100)
                    await page.keyboard.press("Backspace")
                    await page.wait_for_timeout(200)
                    
                    await page.keyboard.type(prompt, delay=20)
                    await page.wait_for_timeout(500)
                    
                    log.info(f"[{self.model_name}] Prompt typed via keyboard")
                    return True
            except Exception as e:
                log.debug(f"[{self.model_name}] Keyboard method failed for {sel}: {e}")
                continue

        log.error(f"[{self.model_name}] Could not type prompt")
        return False

    # ════════════════════════════════════════════════════════
    #  CLICK SUBMIT
    # ════════════════════════════════════════════════════════
    async def _click_submit(self, page) -> bool:
        """Click en botón submit via JS."""
        log.info(f"[{self.model_name}] Clicking submit...")
        
        result = await page.evaluate("""
            () => {
                const selectors = [
                    'button[type="submit"]',
                    'button[aria-label="Enviar"]',
                    'button[aria-label="Send"]',
                    'button:has-text("Enviar")',
                    'button:has-text("Send")',
                ];
                for (const sel of selectors) {
                    try {
                        const btn = document.querySelector(sel);
                        if (btn && !btn.disabled && btn.offsetParent !== null) {
                            btn.click();
                            return { success: true, selector: sel };
                        }
                    } catch (e) {}
                }
                return { success: false };
            }
        """)
        
        if result and result.get('success'):
            log.info(f"[{self.model_name}] Submit clicked ({result.get('selector')})")
            return True
        
        # Fallback: Enter key
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)
        log.info(f"[{self.model_name}] Submit via Enter key")
        return True

    # ════════════════════════════════════════════════════════
    #  WAIT FOR RESPONSE
    # ════════════════════════════════════════════════════════
    async def _wait_for_response(self, page, max_wait: int = 120) -> None:
        """Espera a que la respuesta se estabilice."""
        log.info(f"[{self.model_name}] Waiting for response...")
        
        stable_count = 0
        prev_len = 0
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                current_len = await page.evaluate("""
                    () => {
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
                        for (const sel of selectors) {
                            const els = document.querySelectorAll(sel);
                            if (els.length > 0) {
                                return els[els.length - 1].innerText.length;
                            }
                        }
                        return 0;
                    }""")
                
                if current_len > 50 and current_len == prev_len:
                    stable_count += 1
                    if stable_count >= 3:
                        log.info(f"[{self.model_name}] Response ready ({current_len} chars, stable)")
                        return
                else:
                    stable_count = 0
                    
                prev_len = current_len
            except:
                pass
            
            await asyncio.sleep(1)
        
        log.warning(f"[{self.model_name}] Response wait timeout after {max_wait}s")

    # ════════════════════════════════════════════════════════
    #  EXTRACT RESPONSE
    # ════════════════════════════════════════════════════════
    async def _extract_response(self, page) -> str:
        """Extrae la última respuesta del asistente via JS."""
        log.info(f"[{self.model_name}] Extracting response...")
        
        extract_script = """
        () => {
            const filterWords = [
                'Enviar', 'Send', 'micrófono', 'Nueva conversación', 
                'Ajustes', 'Settings', 'Gemini no es humano',
                'puede cometer errores', 'verifica sus respuestas',
                'Tu privacidad', 'Se abre en una ventana nueva',
                'Mostrar menú', 'Editar petición', 'Detener respuesta',
                'Usar micrófono'
            ];
            
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
                    const last = elements[elements.length - 1];
                    const text = last.innerText || last.textContent;
                    if (text && text.trim().length > 20) {
                        const trimmed = text.trim();
                        const hasFilterWord = filterWords.some(w => trimmed.toLowerCase().includes(w.toLowerCase()));
                        if (!hasFilterWord || trimmed.length > 200) {
                            return trimmed;
                        }
                    }
                }
            }
            
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
            response = await page.evaluate(extract_script)
            if response and len(response) > 20:
                log.info(f"[{self.model_name}] Response extracted ({len(response)} chars)")
                log.debug(f"   Preview: {response[:100]}...")
                return response
        except Exception as e:
            log.debug(f"   Error en extracción JS: {e}")

        log.error(f"[{self.model_name}] No response extracted")
        return ""
