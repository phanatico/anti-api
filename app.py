import json
import logging
import os
import queue
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, session

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv no instalado, usar variables de entorno del sistema

from anti_api import AntiApiChat, normalize_cookies, LOG_DIR, LOG_FILE

# Logging: reutilizar el handler de archivo de anti_api + consola
log = logging.getLogger(__name__)
if not log.handlers:
    from logging.handlers import RotatingFileHandler
    _app_fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    _app_fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    _app_fh.setLevel(logging.DEBUG)
    log.addHandler(_app_fh)
    log.setLevel(logging.DEBUG)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("ANTI_API_SECRET", uuid.uuid4().hex)

# ══════════════════════════════════════════════════════════════════
#  API KEY AUTH — para acceso externo (OpenCloud, bots, etc.)
#  Header: X-API-Key: <key>
#  Las rutas del panel web (/, /static, GET) no requieren API key.
#  Solo endpoints POST /api/* la requieren cuando la petición viene de fuera.
# ══════════════════════════════════════════════════════════════════
API_KEY = os.environ.get("ANTI_API_KEY", "")
MAX_PARALLEL = int(os.environ.get("ANTI_API_MAX_PARALLEL", "10"))


def require_api_key(f):
    """Decorator: exige X-API-Key header si API_KEY está configurada.
    Peticiones desde 127.0.0.1 (panel local) se saltan la verificación."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Peticiones locales (panel web) no necesitan key
        if request.remote_addr in ("127.0.0.1", "::1"):
            return f(*args, **kwargs)
        # Si no hay key configurada, acceso libre
        if not API_KEY:
            return f(*args, **kwargs)
        # Verificar header
        provided = request.headers.get("X-API-Key", "").strip()
        if not provided:
            provided = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if provided != API_KEY:
            return jsonify({"success": False, "error": "API key inválida o ausente. Envía header X-API-Key."}), 401
        return f(*args, **kwargs)
    return decorated

APP_ROOT = os.path.dirname(__file__)
MODELS_PATH = os.path.join(APP_ROOT, "models.json")
ACCOUNTS_PATH = os.path.join(APP_ROOT, "accounts.json")
COOKIE_ROOT = os.path.join(APP_ROOT, "cookies")
DEBUG_ROOT = os.path.join(APP_ROOT, "docs", "debug")
SESSION_ID = uuid.uuid4().hex
SESSION_STARTED_AT = datetime.now()
SESSION_FILE_PATH = os.path.join(
    DEBUG_ROOT,
    SESSION_STARTED_AT.strftime("%Y-%m-%d"),
    f"session-{SESSION_STARTED_AT.strftime('%H%M%S')}_{SESSION_ID}.jsonl",
)

# ══════════════════════════════════════════════════════════════════
#  WORKER THREADS — Playwright sync NO es thread-safe.
#  Cada modelo tiene su propio hilo dedicado con una cola de tareas.
#  Flask encola la tarea y espera el resultado vía threading.Event.
# ══════════════════════════════════════════════════════════════════

class _ModelWorker:
    """
    Worker thread dedicado a un modelo.
    Corre un bucle infinito leyendo tareas de su cola.
    El objeto AntiApiChat vive y muere dentro de este único thread.
    """
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._q: queue.Queue = queue.Queue()
        self._chat: Optional[AntiApiChat] = None
        self._thread = threading.Thread(target=self._loop, name=f"worker-{model_name}", daemon=True)
        self._thread.start()

    def _loop(self):
        while True:
            task = self._q.get()
            if task is None:
                break  # señal de parada
            fn, event, result_box = task
            try:
                result_box["result"] = fn(self._chat)
                result_box["ok"] = True
            except Exception as e:
                result_box["error"] = str(e)
                result_box["traceback"] = traceback.format_exc()
                result_box["ok"] = False
            finally:
                event.set()

    def run(self, fn, timeout: float = 180.0) -> Dict:
        """Encola fn(chat) y espera el resultado. fn recibe el AntiApiChat actual."""
        result_box: Dict = {}
        event = threading.Event()
        self._q.put((fn, event, result_box))
        if not event.wait(timeout=timeout):
            return {"ok": False, "error": f"Timeout ({timeout}s) esperando respuesta del worker"}
        return result_box

    def set_chat(self, chat: Optional[AntiApiChat]):
        """Actualiza el chat desde el worker thread (llamar solo dentro de fn)."""
        self._chat = chat

    def stop(self):
        self._q.put(None)


# Registro global de workers: model_name → _ModelWorker
_workers: Dict[str, _ModelWorker] = {}
_workers_lock = threading.Lock()


def _get_worker(model_name: str) -> _ModelWorker:
    with _workers_lock:
        if model_name not in _workers:
            _workers[model_name] = _ModelWorker(model_name)
        return _workers[model_name]


def verify_cookies_on_startup():
    """Verifica que existan archivos de cookies para cada modelo al arrancar."""
    models = load_models()
    for model in models:
        cookies_file = model.get("cookies_file")
        if cookies_file:
            cookies_path = os.path.join(COOKIE_ROOT, cookies_file)
            if os.path.isfile(cookies_path):
                try:
                    with open(cookies_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, (dict, list)) and len(data) > 0:
                        cookies = normalize_cookies(data)
                        log.info(f"✅ Cookies encontradas para {model['name']}: {len(cookies)} cookies ({', '.join(list(cookies.keys())[:5])})")
                    else:
                        log.warning(f"⚠️ Cookies vacías para {model['name']}")
                except Exception as e:
                    log.warning(f"⚠️ Error leyendo cookies para {model['name']}: {e}")
            else:
                log.warning(f"⚠️ No existe archivo de cookies para {model['name']}: {cookies_path}")


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_models() -> List[Dict[str, Any]]:
    if not os.path.isfile(MODELS_PATH):
        return []
    with open(MODELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_accounts() -> List[Dict[str, Any]]:
    if not os.path.isfile(ACCOUNTS_PATH):
        save_accounts([])
    with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = []
    return data


def save_accounts(accounts: List[Dict[str, Any]]) -> None:
    with open(ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def get_logged_user() -> Optional[Dict[str, Any]]:
    email = session.get("email")
    if not email:
        return None
    accounts = load_accounts()
    return next((account for account in accounts if account.get("email") == email), None)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def cookie_file_path(model_name: str, email: Optional[str] = None) -> str:
    safe_model = model_name.replace("/", "_")
    if email:
        safe_email = normalize_email(email).replace("@", "_")
        return os.path.join(COOKIE_ROOT, safe_email, f"{safe_model}.json")
    return os.path.join(COOKIE_ROOT, f"{safe_model}.json")


def load_cookie_file(path: str) -> Optional[List[Dict[str, Any]]]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cookie_file(path: str, cookies: Any) -> None:
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)


def debug_log(event: str, payload: Dict[str, Any]) -> None:
    ensure_directory(os.path.dirname(SESSION_FILE_PATH))
    entry = {
        "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "session_id": SESSION_ID,
        "event": event,
        "payload": payload,
    }
    with open(SESSION_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def init_debug_log() -> None:
    ensure_directory(os.path.dirname(SESSION_FILE_PATH))
    if not os.path.exists(SESSION_FILE_PATH):
        with open(SESSION_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "session_id": SESSION_ID,
                "started_at": SESSION_STARTED_AT.isoformat(sep=" ", timespec="seconds"),
                "version": "v1.2",
                "event": "session_start",
            }, ensure_ascii=False) + "\n")


init_debug_log()


def find_model(name: str, models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for model in models:
        if model.get("name") == name:
            return model
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/models")
def api_models():
    return jsonify(load_models())


@app.route("/api/send", methods=["POST"])
@require_api_key
def api_send():
    payload              = request.get_json(force=True)
    model_name           = payload.get("model")
    prompt               = payload.get("prompt", "").strip()
    headless             = bool(payload.get("headless", False))
    cookies_from_payload = payload.get("cookies")
    keep_page            = bool(payload.get("keep_page", False))

    if not model_name:
        return jsonify({"success": False, "error": "Falta el nombre del modelo."}), 400
    if not prompt:
        return jsonify({"success": False, "error": "El prompt no puede estar vacío."}), 400

    models_list = load_models()
    model = find_model(model_name, models_list)
    if not model:
        debug_log("send_prompt_error", {"model": model_name, "prompt": prompt, "error": "modelo no encontrado"})
        return jsonify({"success": False, "error": f"No se encontró el modelo '{model_name}'."}), 404

    url      = model.get("url")
    selector = model.get("prompt_selector")
    if not url:
        return jsonify({"success": False, "error": "El modelo no tiene URL configurada."}), 500

    cookies_dict = {}
    if cookies_from_payload:
        cookies_dict = normalize_cookies(cookies_from_payload)

    worker = _get_worker(model_name)

    def task(chat: Optional[AntiApiChat]) -> str:
        """Se ejecuta DENTRO del worker thread — Playwright es thread-safe aquí."""
        if keep_page:
            # Modo conversación continua: reutilizar o crear chat
            if chat is None or not chat._browser or not chat._browser.is_connected():
                chat = AntiApiChat(
                    url=url, model_name=model_name, headless=headless,
                    cookies=cookies_dict, input_selector=selector,
                )
                chat.start()
                worker.set_chat(chat)
            resp = chat.send_prompt(prompt, keep_page=True)
        else:
            # Modo limpio: instancia nueva por request
            chat = AntiApiChat(
                url=url, model_name=model_name, headless=headless,
                cookies=cookies_dict, input_selector=selector,
            )
            try:
                resp = chat.send_prompt(prompt, keep_page=False)
            finally:
                chat.close()
                # En modo limpio no guardamos el chat en el worker
        return resp

    result = worker.run(task, timeout=180.0)

    if result.get("ok"):
        response = result["result"]
        debug_log("send_prompt", {"model": model_name, "prompt": prompt,
                                  "keep_page": keep_page,
                                  "response_preview": (response or "")[:500]})
        return jsonify({"success": True, "response": response, "model": model_name})
    else:
        error_text = result.get("error", "Error desconocido")
        tb_text    = result.get("traceback", "")
        if tb_text:
            print(tb_text)
        # Si falla en modo continuo, limpiar el chat roto dentro del worker
        if keep_page:
            def _reset(chat):
                if chat:
                    try: chat.close()
                    except: pass
                worker.set_chat(None)
            worker.run(_reset, timeout=10.0)
        debug_log("send_prompt_exception", {"model": model_name, "prompt": prompt,
                                            "error": error_text, "traceback": tb_text})
        return jsonify({"success": False, "error": error_text}), 500


@app.route("/api/session/reset", methods=["POST"])
def api_session_reset():
    """Cierra la sesión persistente de un modelo (botón 'Nueva conversación')."""
    payload    = request.get_json(force=True)
    model_name = payload.get("model")
    if not model_name:
        return jsonify({"success": False, "error": "Falta el nombre del modelo."}), 400

    worker = _get_worker(model_name)

    def _do_reset(chat):
        if chat:
            try: chat.close()
            except: pass
        worker.set_chat(None)
        log.info(f"[{model_name}] Sesión reseteada")

    worker.run(_do_reset, timeout=15.0)
    return jsonify({"success": True})


@app.route("/api/validate", methods=["POST"])
@require_api_key
def api_validate():
    """
    Verifica la conexión con el modelo sin enviar un prompt.
    Valida que las cookies funcionen y se pueda acceder al chat.
    """
    payload = request.get_json(force=True)
    model_name = payload.get("model")
    cookies_from_payload = payload.get("cookies")
    headless = bool(payload.get("headless", True))  # Por defecto headless para validación rápida

    if not model_name:
        return jsonify({"success": False, "error": "Falta el nombre del modelo."}), 400

    models = load_models()
    model = find_model(model_name, models)
    if not model:
        return jsonify({"success": False, "error": f"No se encontró el modelo '{model_name}'."}), 404

    url = model.get("url")
    selector = model.get("prompt_selector")
    
    # Normalizar cookies
    cookies_dict = {}
    if cookies_from_payload:
        cookies_dict = normalize_cookies(cookies_from_payload)

    if not url:
        return jsonify({"success": False, "error": "El modelo no tiene URL configurada."}), 500

    # Validate corre en su propio thread desechable (no bloquea el worker del modelo)
    result_box: Dict = {}
    done = threading.Event()

    def _run_validate():
        tmp = None
        try:
            tmp = AntiApiChat(
                url=url, model_name=model_name, headless=headless,
                cookies=cookies_dict, input_selector=selector,
            )
            tmp.start()
            valid, msg = tmp.check_session()
            result_box["valid"] = valid
            result_box["msg"]   = msg
            result_box["ok"]    = True
        except Exception as e:
            result_box["ok"]    = False
            result_box["error"] = str(e)
        finally:
            if tmp:
                try: tmp.close()
                except: pass
            done.set()

    t = threading.Thread(target=_run_validate, daemon=True)
    t.start()
    done.wait(timeout=60.0)

    if not result_box.get("ok"):
        error_text = result_box.get("error", "Timeout o error desconocido")
        debug_log("validate_exception", {"model": model_name, "error": error_text})
        return jsonify({"success": False, "error": error_text}), 500

    if result_box["valid"]:
        debug_log("validate_success", {"model": model_name, "cookies_count": len(cookies_dict)})
        return jsonify({"success": True,
                        "message": "Conexión válida. Cookies funcionando correctamente.",
                        "url": url})
    else:
        debug_log("validate_failed", {"model": model_name, "error": result_box["msg"]})
        return jsonify({"success": False,
                        "error": f"Conexión fallida: {result_box['msg']}",
                        "url": url}), 401


@app.route("/api/account/register", methods=["POST"])
def api_account_register():
    payload = request.get_json(force=True)
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "").strip()
    name = payload.get("name", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email y contraseña son obligatorios."}), 400

    accounts = load_accounts()
    if any(account.get("email") == email for account in accounts):
        return jsonify({"success": False, "error": "Ya existe una cuenta con ese email."}), 409

    verification_code = uuid.uuid4().hex[:8]
    account = {
        "id": uuid.uuid4().hex,
        "email": email,
        "name": name,
        "password": password,
        "verified": False,
        "verification_code": verification_code,
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    accounts.append(account)
    save_accounts(accounts)
    debug_log("account_register", {"email": email, "name": name, "verified": False})
    return jsonify({"success": True, "account_id": account["id"], "verification_code": verification_code})


@app.route("/api/account/verify", methods=["POST"])
def api_account_verify():
    payload = request.get_json(force=True)
    email = payload.get("email", "").strip().lower()
    code = payload.get("code", "").strip()

    if not email or not code:
        return jsonify({"success": False, "error": "Email y código de verificación son obligatorios."}), 400

    accounts = load_accounts()
    account = next((item for item in accounts if item.get("email") == email), None)
    if not account:
        return jsonify({"success": False, "error": "Cuenta no encontrada."}), 404

    if account.get("verification_code") != code:
        debug_log("account_verify_fail", {"email": email, "code": code})
        return jsonify({"success": False, "error": "Código de verificación incorrecto."}), 400

    account["verified"] = True
    save_accounts(accounts)
    debug_log("account_verify", {"email": email, "verified": True})
    return jsonify({"success": True, "verified": True})


@app.route("/api/account/login", methods=["POST"])
def api_account_login():
    payload = request.get_json(force=True)
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email y contraseña son obligatorios."}), 400

    accounts = load_accounts()
    account = next((item for item in accounts if item.get("email") == email), None)
    if not account or account.get("password") != password:
        return jsonify({"success": False, "error": "Email o contraseña incorrectos."}), 401

    if not account.get("verified"):
        return jsonify({"success": False, "error": "Cuenta no verificada."}), 403

    session["email"] = email
    debug_log("account_login", {"email": email})
    return jsonify({"success": True, "email": email, "name": account.get("name", ""), "verified": True})


@app.route("/api/account/logout", methods=["POST"])
def api_account_logout():
    session.pop("email", None)
    return jsonify({"success": True})


@app.route("/api/account/status", methods=["GET"])
def api_account_status():
    user = get_logged_user()
    if not user:
        return jsonify({"success": True, "logged_in": False})
    return jsonify({
        "success": True,
        "logged_in": True,
        "email": user["email"],
        "name": user.get("name", ""),
        "verified": user.get("verified", False),
    })


@app.route("/api/model/cookies", methods=["GET"])
def api_model_cookies_get():
    model_name = request.args.get("model")
    if not model_name:
        return jsonify({"success": False, "error": "Falta el nombre del modelo."}), 400

    model = find_model(model_name, load_models())
    if not model:
        return jsonify({"success": False, "error": f"No se encontró el modelo '{model_name}'."}), 404

    user = get_logged_user()
    cookies_file = cookie_file_path(model_name, user.get("email") if user else None)
    cookies = load_cookie_file(cookies_file)
    if not cookies:
        return jsonify({"success": False, "error": "No se encontró cookies guardadas para este modelo."}), 404

    return jsonify({"success": True, "cookies": cookies, "cookies_file": cookies_file})


@app.route("/api/model/cookies", methods=["POST"])
def api_model_cookies_save():
    user = get_logged_user()
    if not user:
        return jsonify({"success": False, "error": "Debes iniciar sesión para guardar cookies."}), 401

    payload = request.get_json(force=True)
    model_name = payload.get("model")
    cookies = payload.get("cookies")

    if not model_name or not cookies:
        return jsonify({"success": False, "error": "Modelo y cookies son obligatorios."}), 400
    if not isinstance(cookies, list):
        return jsonify({"success": False, "error": "Las cookies deben ser un arreglo JSON."}), 400

    cookies_file = cookie_file_path(model_name, user["email"])
    save_cookie_file(cookies_file, cookies)
    debug_log("model_cookies_saved", {"email": user["email"], "model": model_name, "cookies_file": cookies_file})
    return jsonify({"success": True, "cookies_file": cookies_file})


# ══════════════════════════════════════════════════════════════════
#  BATCH ENDPOINT — Enviar N prompts en paralelo
#  Ideal para OpenCloud: envía 10 preguntas, recibe 10 respuestas.
#  Cada una corre en su propio navegador (thread-pool).
# ══════════════════════════════════════════════════════════════════

@app.route("/api/batch", methods=["POST"])
@require_api_key
def api_batch():
    """
    Envía múltiples prompts en paralelo.
    Body JSON:
    {
        "queries": [
            {"model": "gemini", "prompt": "¿Qué es Python?"},
            {"model": "grok",   "prompt": "Explica Docker"},
            {"model": "gemini", "prompt": "¿Qué es Kubernetes?"}
        ],
        "headless": true
    }
    Respuesta:
    {
        "success": true,
        "results": [
            {"index": 0, "model": "gemini", "prompt": "...", "success": true, "response": "..."},
            {"index": 1, "model": "grok",   "prompt": "...", "success": true, "response": "..."},
            ...
        ]
    }
    """
    payload = request.get_json(force=True)
    queries = payload.get("queries", [])
    headless = bool(payload.get("headless", True))

    if not queries or not isinstance(queries, list):
        return jsonify({"success": False, "error": "Envía 'queries': [{model, prompt}, ...]"}), 400

    if len(queries) > MAX_PARALLEL:
        return jsonify({"success": False, "error": f"Máximo {MAX_PARALLEL} queries por batch."}), 400

    models_list = load_models()

    def run_single(idx: int, q: dict) -> dict:
        """Ejecuta una query individual en su propio browser."""
        model_name = q.get("model", "")
        prompt = q.get("prompt", "").strip()
        result = {"index": idx, "model": model_name, "prompt": prompt}

        if not model_name or not prompt:
            result["success"] = False
            result["error"] = "Falta model o prompt"
            return result

        model = find_model(model_name, models_list)
        if not model:
            result["success"] = False
            result["error"] = f"Modelo '{model_name}' no encontrado"
            return result

        url = model.get("url")
        selector = model.get("prompt_selector")
        cookies_file = model.get("cookies_file")

        cookies_dict = {}
        if cookies_file:
            cpath = os.path.join(COOKIE_ROOT, cookies_file)
            raw = load_cookie_file(cpath)
            if raw:
                cookies_dict = normalize_cookies(raw)

        chat = None
        try:
            chat = AntiApiChat(
                url=url, model_name=model_name, headless=headless,
                cookies=cookies_dict, input_selector=selector,
            )
            resp = chat.send_prompt(prompt, keep_page=False)
            result["success"] = True
            result["response"] = resp
            result["chars"] = len(resp) if resp else 0
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        finally:
            if chat:
                try:
                    chat.close()
                except:
                    pass
        return result

    log.info(f"[BATCH] Procesando {len(queries)} queries en paralelo (max_workers={min(len(queries), MAX_PARALLEL)})")
    results = []

    with ThreadPoolExecutor(max_workers=min(len(queries), MAX_PARALLEL)) as executor:
        futures = {executor.submit(run_single, i, q): i for i, q in enumerate(queries)}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                idx = futures[future]
                results.append({"index": idx, "success": False, "error": str(e)})

    results.sort(key=lambda r: r["index"])
    ok_count = sum(1 for r in results if r.get("success"))
    log.info(f"[BATCH] Completado: {ok_count}/{len(results)} exitosos")

    debug_log("batch_send", {
        "total": len(queries),
        "ok": ok_count,
        "queries": [{"model": q.get("model"), "prompt": q.get("prompt", "")[:50]} for q in queries],
    })

    return jsonify({"success": True, "results": results, "total": len(results), "ok": ok_count})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Health check — para que OpenCloud verifique que ANTI-API está vivo."""
    return jsonify({
        "status": "ok",
        "version": "1.3",
        "session_id": SESSION_ID,
        "uptime_since": SESSION_STARTED_AT.isoformat(sep=" ", timespec="seconds"),
        "models": [m["name"] for m in load_models()],
        "max_parallel": MAX_PARALLEL,
        "api_key_configured": bool(API_KEY),
    })


if __name__ == "__main__":
    ensure_directory(COOKIE_ROOT)
    ensure_directory(DEBUG_ROOT)
    verify_cookies_on_startup()
    HOST = os.environ.get("ANTI_API_HOST", "0.0.0.0")
    PORT = int(os.environ.get("ANTI_API_PORT", "4000"))
    log.info(f"Starting ANTI-API on {HOST}:{PORT} (API key: {'configured' if API_KEY else 'OPEN'})")
    # threaded=True permite peticiones paralelas a distintos modelos
    app.run(host=HOST, port=PORT, debug=True, threaded=True)
