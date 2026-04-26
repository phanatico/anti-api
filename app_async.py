"""
ANTI-API - Async Server (FastAPI)
Soporta múltiples requests concurrentes usando Playwright async.
"""
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from anti_api_async import AntiApiChatAsync, normalize_cookies

log = logging.getLogger(__name__)
APP_ROOT = os.path.dirname(__file__)
MODELS_PATH = os.path.join(APP_ROOT, "models.json")
COOKIE_ROOT = os.path.join(APP_ROOT, "cookies")

# Instancia global de chat (reutilizada entre requests)
_chat_instances: Dict[str, AntiApiChatAsync] = {}


class SendPromptRequest(BaseModel):
    model: str
    prompt: str
    headless: bool = True
    cookies: Optional[Dict[str, str]] = None


class SendPromptResponse(BaseModel):
    success: bool
    response: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    log.info("Starting ANTI-API Async Server...")
    os.makedirs(COOKIE_ROOT, exist_ok=True)
    
    # Iniciar instancias de chat para cada modelo
    models = load_models()
    for model in models:
        model_name = model["name"]
        cookies_file = model.get("cookies_file")
        if cookies_file:
            cookies_path = os.path.join(COOKIE_ROOT, cookies_file)
            if os.path.isfile(cookies_path):
                try:
                    with open(cookies_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cookies = normalize_cookies(data)
                    if cookies:
                        chat = AntiApiChatAsync(
                            url=model["url"],
                            model_name=model_name,
                            headless=True,
                            cookies=cookies,
                            input_selector=model.get("prompt_selector"),
                        )
                        await chat.start(max_tabs=10)  # 10 tabs en paralelo
                        _chat_instances[model_name] = chat
                        log.info(f"✅ Chat instance started for {model_name}")
                except Exception as e:
                    log.warning(f"⚠️ Failed to start chat for {model_name}: {e}")
    
    yield
    
    # Shutdown: cerrar todas las instancias
    log.info("Shutting down chat instances...")
    for chat in _chat_instances.values():
        await chat.stop()
    _chat_instances.clear()


app = FastAPI(lifespan=lifespan)

# CORS para permitir requests desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_models() -> List[Dict[str, Any]]:
    if not os.path.isfile(MODELS_PATH):
        return []
    with open(MODELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_model(name: str, models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for model in models:
        if model.get("name") == name:
            return model
    return None


@app.get("/")
async def root():
    return {"message": "ANTI-API Async Server", "status": "running"}


@app.get("/api/models")
async def get_models():
    return load_models()


@app.post("/api/send", response_model=SendPromptResponse)
async def send_prompt(request: SendPromptRequest):
    model_name = request.model
    prompt = request.prompt.strip()
    headless = request.headless
    cookies_from_payload = request.cookies

    if not model_name:
        raise HTTPException(status_code=400, detail="Falta el nombre del modelo.")
    if not prompt:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío.")

    models = load_models()
    model = find_model(model_name, models)
    if not model:
        raise HTTPException(status_code=404, detail=f"No se encontró el modelo '{model_name}'.")

    url = model.get("url")
    selector = model.get("prompt_selector")

    # Normalizar cookies
    cookies_dict = {}
    if cookies_from_payload:
        cookies_dict = normalize_cookies(cookies_from_payload)

    if not url:
        raise HTTPException(status_code=500, detail="El modelo no tiene URL configurada.")

    try:
        # Usar cookies del payload si se proporcionan, sino usar instancia global
        if cookies_dict:
            chat = AntiApiChatAsync(
                url=url,
                model_name=model_name,
                headless=headless,
                cookies=cookies_dict,
                input_selector=selector,
            )
            await chat.start(max_tabs=10)
            response = await chat.send_prompt(prompt)
            await chat.stop()
        else:
            # Reutilizar instancia global
            if model_name not in _chat_instances:
                raise HTTPException(status_code=404, detail=f"No hay instancia de chat para {model_name}. Proporciona cookies.")
            chat = _chat_instances[model_name]
            response = await chat.send_prompt(prompt)
        
        return SendPromptResponse(success=True, response=response, model=model_name)
    except Exception as exc:
        log.error(f"Error in send_prompt: {exc}")
        return SendPromptResponse(success=False, error=str(exc), model=model_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=4000)
