# Diseño: Panel web local para chat IA vía Playwright

## Objetivo
Crear un panel web local que funcione como una "pseudo-API" para webchats de IA como Gemini.
El panel permitirá:
- seleccionar entre varios modelos/configuraciones
- enviar un prompt manualmente
- obtener la respuesta del chat en pantalla
- mantener la sesión con cookies JSON

## Arquitectura

1. Frontend ligero (HTML/CSS/JS)
   - formulario para elegir modelo y escribir prompt
   - área de resultados para mostrar respuesta
   - botón para enviar

2. Backend Python con Flask
   - servidor local que expone una ruta web
   - recibe requests desde el frontend
   - gestiona sesiones con Playwright
   - devuelve respuesta JSON al panel

3. Configuración de modelos
   - archivo `models.json`
   - cada modelo contiene:
     - nombre
     - URL del chat web
     - selector del prompt
     - ruta a cookies JSON
     - descripción opcional

4. Manejador de sesión Playwright
   - abre navegador Chromium
   - carga cookies para mantener sesión
   - navega a la URL del modelo
   - escribe el prompt y envía
   - espera y extrae la respuesta
   - cierra el navegador después de la llamada o mantiene sesión activa

## Flujo de datos

1. Usuario abre el panel local.
2. Escoge un modelo y escribe un prompt.
3. Envía el prompt.
4. Frontend hace POST a `/api/send`.
5. Backend carga la configuración del modelo.
6. Backend usa Playwright para automatizar el chat.
7. Extrae la respuesta y la envía al frontend.
8. Frontend muestra la respuesta en pantalla.

## Consideraciones

- Usar cookies JSON para mantener sesión y evitar login manual.
- Estructura de selectores flexible: permitir editar el selector del prompt por modelo.
- Incluir mensajes de error claros para fallos de selector, carga de cookies o tiempo de espera.
- Evitar bloqueos con delays humanos simples.

## Archivos principales

- `app.py` — servidor Flask y API local
- `anti_api.py` — clase de automatización Playwright reutilizable
- `models.json` — configuraciones de modelos/chat
- `templates/index.html` — interfaz web
- `static/styles.css` — estilo básico
- `static/app.js` — lógica de frontend

## Siguiente paso
Implementar el backend Flask, el frontend y un modelo de ejemplo para Gemini.
