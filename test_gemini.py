#!/usr/bin/env python3
"""
Script de prueba para Gemini - ANTI-API
Sistema de cookies simple (estilo Grok) - JSON clave-valor

Uso: 
  # Con archivo de cookies simple (formato dict)
  python test_gemini.py --cookies cookies_gemini.json --prompt "Hola"

  # Con cookies en formato array de navegador
  python test_gemini.py --cookies cookies_array.json --prompt "Hola"

Formato de cookies esperado (cualquiera de estos):
  1. Dict simple: {"__Secure-1PSID": "valor", "NID": "valor"}
  2. Array: [{"name": "__Secure-1PSID", "value": "valor"}, ...]
"""

import argparse
import json
import os
import sys

from anti_api import AntiApiChat, normalize_cookies


def main():
    parser = argparse.ArgumentParser(description="Probar Gemini con ANTI-API")
    parser.add_argument(
        "--cookies", 
        required=True, 
        help="Ruta al archivo JSON de cookies (formato simple dict o array)"
    )
    parser.add_argument(
        "--prompt", 
        default="Hola, ¿qué puedes hacer?", 
        help="Prompt a enviar"
    )
    parser.add_argument(
        "--headless", 
        action="store_true", 
        help="Modo headless (sin ventana)"
    )
    args = parser.parse_args()

    # Cargar y normalizar cookies
    if not os.path.isfile(args.cookies):
        print(f"❌ Error: No se encontró el archivo de cookies: {args.cookies}")
        print("\n💡 Para obtener cookies de Gemini:")
        print("   1. Abre Chrome y ve a https://gemini.google.com")
        print("   2. Inicia sesión con tu cuenta de Google")
        print("   3. Instala la extensión 'Cookie Editor'")
        print("   4. Exporta las cookies en formato JSON")
        print("   5. El archivo puede ser:")
        print("      - Dict simple: {\"cookie1\":\"valor\", \"cookie2\":\"valor\"}")
        print("      - Array completo: [{\"name\":...}, ...]")
        sys.exit(1)

    # Cargar cookies desde archivo
    with open(args.cookies, "r", encoding="utf-8") as f:
        raw_cookies = json.load(f)
    
    # Normalizar al formato dict simple
    cookies_dict = normalize_cookies(raw_cookies)
    
    if not cookies_dict:
        print("❌ Error: No se pudieron extraer cookies del archivo")
        print("   Asegúrate de que el JSON tenga el formato correcto")
        sys.exit(1)

    print(f"🚀 Iniciando prueba con Gemini...")
    print(f"📄 Cookies cargadas: {len(cookies_dict)} cookies")
    print(f"🔑 Cookies: {', '.join(cookies_dict.keys())}")
    print(f"💬 Prompt: {args.prompt}")
    print(f"👁️  Headless: {args.headless}")
    print("-" * 50)

    chat = None
    try:
        # Crear instancia con sistema nuevo de cookies
        chat = AntiApiChat(
            url="https://gemini.google.com/",
            model_name="gemini",
            headless=args.headless,
            cookies=cookies_dict,
            input_selector="div[contenteditable='true']",
        )

        print("✅ Navegador iniciado y cookies inyectadas")
        print("📤 Enviando prompt...")

        response = chat.send_prompt(args.prompt)

        print("\n" + "=" * 50)
        print("📥 RESPUESTA DE GEMINI:")
        print("=" * 50)
        print(response)
        print("=" * 50)

        # Guardar respuesta en archivo
        resultado = {
            "prompt": args.prompt,
            "response": response,
            "success": bool(response.strip()),
            "cookies_used": list(cookies_dict.keys()),
        }

        output_file = "test_gemini_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Resultado guardado en: {output_file}")

        if response.strip():
            print("\n✅ Prueba EXITOSA")
            return 0
        else:
            print("\n⚠️  Prueba completada pero respuesta vacía")
            return 1

    except KeyboardInterrupt:
        print("\n\n⛔ Cancelado por usuario")
        return 130
    except Exception as e:
        print(f"\n❌ Error durante la prueba: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if chat:
            print("\n🔒 Cerrando navegador...")
            chat.close()


if __name__ == "__main__":
    sys.exit(main())
