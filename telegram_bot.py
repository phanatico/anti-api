"""
ANTI-API - Telegram Bot
Bot de Telegram con sistema de numeración Q&A.
Usa la API async de ANTI-API para respuestas rápidas.
"""
import asyncio
import json
import logging
import os
from typing import Dict, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from anti_api_async import AntiApiChatAsync, normalize_cookies

# Configuración
ANTI_API_URL = "http://127.0.0.1:4000"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
COOKIE_ROOT = os.path.join(os.path.dirname(__file__), "cookies")

# Historial de conversaciones por usuario
# {user_id: {qa_counter: int, qa_history: [{number, question, answer, model, timestamp}]}}
_conversations: Dict[int, Dict] = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
log = logging.getLogger(__name__)


def load_cookies(model_name: str) -> Optional[Dict[str, str]]:
    """Carga cookies desde archivo."""
    cookies_file = f"cookies_{model_name}.json"
    cookies_path = os.path.join(COOKIE_ROOT, cookies_file)
    
    if not os.path.isfile(cookies_path):
        return None
    
    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_cookies(data)
    except Exception as e:
        log.error(f"Error loading cookies for {model_name}: {e}")
        return None


async def send_prompt_async(model: str, prompt: str, cookies: Dict[str, str]) -> str:
    """Envía prompt usando ANTI-API async."""
    chat = AntiApiChatAsync(
        url="https://grok.com/" if model == "grok" else "https://www.meta.ai/",
        model_name=model,
        headless=True,
        cookies=cookies,
    )
    await chat.start(max_tabs=10)
    try:
        response = await chat.send_prompt(prompt)
        return response
    finally:
        await chat.stop()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - inicializa conversación."""
    user_id = update.effective_user.id
    _conversations[user_id] = {"qa_counter": 0, "qa_history": []}
    
    await update.message.reply_text(
        "🤖 *ANTI-API Bot*\n\n"
        "Usa:\n"
        "/grok - Usar Grok (xAI)\n"
        "/meta - Usar Meta AI\n"
        "/history - Ver historial\n"
        "/clear - Limpiar historial\n\n"
        "O escribe directamente para usar el modelo por defecto (Grok).",
        parse_mode="Markdown"
    )


async def grok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /grok - cambia a modelo Grok."""
    user_id = update.effective_user.id
    if user_id not in _conversations:
        _conversations[user_id] = {"qa_counter": 0, "qa_history": []}
    _conversations[user_id]["model"] = "grok"
    await update.message.reply_text("🔵 Modelo cambiado a *Grok* (xAI)", parse_mode="Markdown")


async def meta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /meta - cambia a modelo Meta."""
    user_id = update.effective_user.id
    if user_id not in _conversations:
        _conversations[user_id] = {"qa_counter": 0, "qa_history": []}
    _conversations[user_id]["model"] = "meta"
    await update.message.reply_text("🟣 Modelo cambiado a *Meta AI*", parse_mode="Markdown")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /history - muestra historial."""
    user_id = update.effective_user.id
    if user_id not in _conversations or not _conversations[user_id]["qa_history"]:
        await update.message.reply_text("📭 No hay historial aún.")
        return
    
    history = _conversations[user_id]["qa_history"]
    response = "📜 *Historial:*\n\n"
    
    for entry in history[-5:]:  # Últimas 5
        response += f"📝 *P{entry['number']}* ({entry['model'].upper()}): {entry['question'][:50]}...\n"
        response += f"💬 *R{entry['number']}*: {entry['answer'][:50]}...\n\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /clear - limpia historial."""
    user_id = update.effective_user.id
    if user_id in _conversations:
        _conversations[user_id]["qa_counter"] = 0
        _conversations[user_id]["qa_history"] = []
    await update.message.reply_text("🗑️ Historial limpiado.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto - envía prompt al modelo."""
    user_id = update.effective_user.id
    prompt = update.message.text
    
    # Inicializar conversación si no existe
    if user_id not in _conversations:
        _conversations[user_id] = {"qa_counter": 0, "qa_history": []}
    
    # Determinar modelo (default: grok)
    model = _conversations[user_id].get("model", "grok")
    
    # Cargar cookies
    cookies = load_cookies(model)
    if not cookies:
        await update.message.reply_text(
            f"❌ No hay cookies para {model.upper()}. "
            f"Guarda cookies en cookies/cookies_{model}.json"
        )
        return
    
    # Enviar "escribiendo..."
    await update.message.chat.send_action("typing")
    
    try:
        # Enviar prompt
        response = await send_prompt_async(model, prompt, cookies)
        
        if not response:
            await update.message.reply_text("❌ No se obtuvo respuesta. Intenta de nuevo.")
            return
        
        # Incrementar contador y guardar en historial
        _conversations[user_id]["qa_counter"] += 1
        qa_number = _conversations[user_id]["qa_counter"]
        
        qa_entry = {
            "number": qa_number,
            "question": prompt,
            "answer": response,
            "model": model,
            "timestamp": str(update.message.date)
        }
        _conversations[user_id]["qa_history"].append(qa_entry)
        
        # Formatear respuesta con numeración
        formatted_response = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 *Pregunta {qa_number}* ({model.upper()}):\n"
            f"{prompt}\n\n"
            f"💬 *Respuesta {qa_number}*:\n"
            f"{response}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        await update.message.reply_text(formatted_response, parse_mode="Markdown")
        
    except Exception as e:
        log.error(f"Error handling message: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


def main():
    """Inicia el bot de Telegram."""
    if TELEGRAM_TOKEN == "TU_TOKEN_AQUI":
        print("❌ ERROR: Configura TELEGRAM_TOKEN en variables de entorno")
        print("   export TELEGRAM_TOKEN='tu_token_aqui'")
        return
    
    # Crear aplicación
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("grok", grok_command))
    app.add_handler(CommandHandler("meta", meta_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Iniciar bot
    log.info("🤖 Iniciando bot de Telegram...")
    app.run_polling()


if __name__ == "__main__":
    main()
