"""
Script de prueba para enviar prompt a Meta directamente desde Python.
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
        with open('cookies_meta.json', 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        print(f"✅ Cookies cargadas: {len(cookies)}")
    except FileNotFoundError:
        print("❌ No se encontró cookies_meta.json")
        print("   Primero obtén las cookies con: python get_cookies.py --model meta --output cookies_meta.json")
        return

    # Prompt a enviar
    prompt = """mentalidad financiera

hábitos de los ricos

por qué no ahorro

trampa del consumismo

psicología del dinero"""

    print(f"\n📤 Prompt: {prompt[:100]}...")
    print("="*60)

    # Crear instancia de chat
    chat = AntiApiChat(
        url='https://www.meta.ai/',
        model_name='meta',
        headless=True,  # Sin abrir navegador visible
        cookies=cookies,
        validate_session=False,  # Puentear validación, usar cookies directamente
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
