"""
Script de prueba para enviar prompt a Gemini directamente desde Python.
"""
import json
import logging
from anti_api import AntiApiChat

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    # Cargar cookies (formato dict simple)
    try:
        with open('cookies_gemini.json', 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        print(f"✅ Cookies cargadas: {len(cookies)}")
    except FileNotFoundError:
        print("❌ No se encontró cookies_gemini.json")
        print("   Primero obtén las cookies con: python get_cookies.py --model gemini")
        return

    # Prompt a enviar
    prompt = """enumera los comandos crea historial crea un songoku futurista estilo terminator con un dragon con las bolas tambien mitad terminator luego en respuesta recopia pregunta con su numero y su respuesta!"""

    print(f"\n📤 Prompt: {prompt[:100]}...")
    print("="*60)

    # Crear instancia de chat
    chat = AntiApiChat(
        url='https://gemini.google.com/',
        model_name='gemini',
        headless=True,  # Sin abrir navegador visible
        cookies=cookies
    )

    try:
        # Enviar prompt
        response = chat.send_prompt(prompt)
        
        print("\n" + "="*60)
        print("✅ RESPUESTA RECIBIDA")
        print("="*60)
        print(response)
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        chat.close()

if __name__ == "__main__":
    main()
