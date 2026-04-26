#!/usr/bin/env python3
"""
Helper para obtener cookies de Gemini/ChatGPT/Grok
Abre el navegador, espera a que hagas login manualmente, y guarda las cookies.

Uso: python get_cookies.py --model gemini --output cookies_gemini.json
"""

import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(
        description="Obtener cookies de sesión de chats de IA"
    )
    parser.add_argument(
        "--model",
        choices=["gemini", "grok", "meta"],
        required=True,
        help="Modelo para el cual obtener cookies",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta donde guardar las cookies (default: cookies/cookies_{model}.json)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=60,
        help="Segundos de espera después del login (default: 60)",
    )
    args = parser.parse_args()

    # URLs por modelo
    urls = {
        "gemini": "https://gemini.google.com/",
        "grok": "https://grok.com/",
        "meta": "https://www.meta.ai/",
    }

    url = urls[args.model]

    # Default output: cookies/cookies_{model}.json
    if args.output is None:
        args.output = os.path.join("cookies", f"cookies_{args.model}.json")

    print(f"🌐 Abriendo {url}")
    print(f"⏱️  Tienes {args.wait} segundos para hacer login manualmente")
    print("💡 Instrucciones:")
    print("   1. Ingresa tus credenciales en el navegador")
    print("   2. Espera a que cargue completamente el chat")
    print("   3. El programa guardará las cookies automáticamente")
    print("-" * 50)

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()

    try:
        page.goto(url, wait_until="networkidle")
        print(f"\n✅ Página cargada. Por favor, haz login manualmente.")
        print(f"� IMPORTANTE: Escribe un mensaje en el chat para asegurar sesión activa")
        print(f"�🕐 Esperando {args.wait} segundos...")

        # Contador regresivo
        for i in range(args.wait, 0, -1):
            if i % 10 == 0 or i <= 5:
                print(f"   Guardando en {i} segundos...", end="\r")
            time.sleep(1)

        print("\n💾 Guardando cookies...")

        # Obtener cookies del navegador
        cookies_array = context.cookies()
        
        # Convertir a formato simple dict (estilo Grok system) para fácil copiar/pegar
        cookies_simple = {}
        for cookie in cookies_array:
            cookies_simple[cookie["name"]] = cookie["value"]

        # Asegurar que existe el directorio
        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Guardar en formato simple (dict)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(cookies_simple, f, indent=2, ensure_ascii=False)

        print(f"✅ Cookies guardadas en: {args.output}")
        print(f"📊 Total de cookies: {len(cookies_simple)}")
        
        # También guardar versión completa con dominios (por compatibilidad)
        output_full = args.output.replace(".json", "_full.json")
        with open(output_full, "w", encoding="utf-8") as f:
            json.dump(cookies_array, f, indent=2, ensure_ascii=False)
        print(f"📋 Versión completa guardada en: {output_full}")

        # Mostrar algunas cookies importantes
        important_patterns = ["__Secure-", "session", "token", "auth", "sso", "PSID", "NID"]
        found = {k: v for k, v in cookies_simple.items() if any(i in k for i in important_patterns)}
        if found:
            print("\n🔐 Cookies de sesión importantes:")
            for name, value in list(found.items())[:5]:
                print(f"   - {name}: {value[:40]}...")

        return 0

    except KeyboardInterrupt:
        print("\n\n⛔ Cancelado por usuario")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    finally:
        context.close()
        browser.close()
        playwright.stop()
        print("\n🔒 Navegador cerrado")


if __name__ == "__main__":
    sys.exit(main())
