"""
Script para verificar que las cookies funcionan antes de usar el panel web.
Uso: python verify_cookies.py --model grok --cookies cookies_grok.json
"""
import argparse
import json
import sys
from anti_api import AntiApiChat, normalize_cookies

def main():
    parser = argparse.ArgumentParser(description="Verificar cookies de chat IA")
    parser.add_argument("--model", required=True, choices=["grok", "gemini", "meta"])
    parser.add_argument("--cookies", required=True, help="Archivo JSON con cookies")
    args = parser.parse_args()

    # Cargar cookies
    try:
        with open(args.cookies, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = normalize_cookies(data)
        print(f"✅ Cookies cargadas: {len(cookies)} encontradas")
        print(f"   Nombres: {', '.join(list(cookies.keys())[:5])}")
    except Exception as e:
        print(f"❌ Error cargando cookies: {e}")
        sys.exit(1)

    # URLs por modelo
    urls = {
        "grok": "https://grok.com",
        "gemini": "https://gemini.google.com",
        "meta": "https://www.meta.ai",
    }

    print(f"\n🔍 Verificando conexión con {args.model}...")
    print("=" * 50)

    chat = AntiApiChat(
        url=urls[args.model],
        model_name=args.model,
        headless=False,  # Visible para ver qué pasa
        cookies=cookies,
    )

    try:
        chat.start()
        valid, msg = chat.check_session()
        
        if valid:
            print("\n" + "=" * 50)
            print("✅ COOKIES VÁLIDAS - Conexión exitosa")
            print("=" * 50)
            print(f"Puedes usar estas cookies en el panel web.")
        else:
            print("\n" + "=" * 50)
            print("❌ COOKIES INVÁLIDAS")
            print("=" * 50)
            print(f"Error: {msg}")
            print("\nSolución:")
            print(f"  python get_cookies.py --model {args.model} --output {args.cookies} --wait 120")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error durante verificación: {e}")
        sys.exit(1)
    finally:
        chat.close()

if __name__ == "__main__":
    main()
