"""
Test directo de Meta AI - sin panel web, solo Python.
Uso: python test_direct.py --cookies cookies_meta.json
"""
import argparse
import json
from anti_api import AntiApiChat, normalize_cookies

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookies", default="cookies_meta.json", help="Archivo de cookies")
    parser.add_argument("--prompt", default="Hola, ¿cómo estás?", help="Prompt a enviar")
    parser.add_argument("--visible", action="store_true", help="Mostrar navegador (para debug)")
    args = parser.parse_args()

    # Cargar cookies
    try:
        with open(args.cookies, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = normalize_cookies(data)
        print(f"✅ Cookies cargadas: {len(cookies)}")
        print(f"   {list(cookies.keys())}")
    except Exception as e:
        print(f"❌ Error cargando cookies: {e}")
        return

    print(f"\n🚀 Iniciando test con Meta AI...")
    print(f"   URL: https://www.meta.ai/")
    print(f"   Headless: {not args.visible}")
    print(f"   Prompt: '{args.prompt}'")
    print("="*50)

    chat = AntiApiChat(
        url="https://www.meta.ai/",
        model_name="meta",
        headless=not args.visible,
        cookies=cookies,
    )

    try:
        response = chat.send_prompt(args.prompt)
        
        print("\n" + "="*50)
        if response:
            print(f"✅ RESPUESTA RECIBIDA ({len(response)} caracteres):")
            print("="*50)
            print(response[:500] + "..." if len(response) > 500 else response)
        else:
            print("❌ Sin respuesta")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        chat.close()

if __name__ == "__main__":
    main()
