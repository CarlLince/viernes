# Viernes

Agente de terminal por voz para Termux (Android) con Gemini. Le hablas, entiende la orden y ejecuta comandos en tu teléfono, siempre con tu confirmación.

## Características
- Alterna entre modo voz y modo escritura.
- Cambio automático de modelo de Gemini, con aviso.
- Comandos con confirmación, lista de bloqueo y filtro de secretos.
- Voz con edge-tts (`es-CL-CatalinaNeural`); el código incluye también gTTS y la voz del teléfono.
- Opcional: la app [Viernes Escucha](https://github.com/CarlLince/viernes-escucha) lo lanza con dos aplausos y la palabra «viernes».

## Instalación
    pkg install python termux-api ffmpeg mpv
    pip install -r requirements.txt

Necesitas también la app **Termux:API** en Android. Opcional: `pkg install yt-dlp` para reproducir música.

## Configuración
    export GEMINI_API_KEY="tu_clave"

Saca la clave en Google AI Studio. Nunca la escribas en el código ni la subas al repositorio.

## Uso
    python viernes.py

## Seguridad
Viernes ejecuta comandos en tu teléfono: lee cada confirmación antes de aceptar. Los audios temporales se borran al salir. Úsalo bajo tu propia responsabilidad.

## Licencia
MIT

## Instalación rápida (Termux)

```
pkg install -y curl && curl -fsSL https://raw.githubusercontent.com/CarlLince/viernes/main/instalar.sh | bash
```

El instalador pone los paquetes, baja Viernes, te pide tu clave de Gemini, crea el comando `viernes`, ajusta Termux y descarga la app **Viernes Escucha** (aplausos, palabra «viernes», cara flotante y control de pantalla).

## Control de pantalla

`pantalla.py` lee la pantalla y simula toques usando el servicio de accesibilidad de la app Viernes Escucha. Solo habla con `127.0.0.1` y con una clave que se guarda al tocar «Vincular pantalla con Termux». Las instrucciones para el agente están en `notas_pantalla.txt`; el instalador las agrega a tu `notas.txt`.

`seguridad.py` decide qué corre solo, qué pide permiso (borrar, claves, SMS, llamadas, cámara, micrófono, ssh, sudo...) y qué se bloquea siempre (lo destructivo). Pruébalo con `python seguridad.py` o `python seguridad.py "rm archivo.txt"`.
