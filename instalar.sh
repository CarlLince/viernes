#!/data/data/com.termux/files/usr/bin/bash
# Instalador de Viernes para Termux (agente + cara + seguridad + control de pantalla + app Viernes Escucha)
# Uso:  bash instalar.sh              (instala todo, también descarga la app Viernes Escucha)
#       bash instalar.sh --sin-app    (no descarga el APK)
# Requisito: tener instaladas las apps Termux y Termux:API (misma fuente: F-Droid o GitHub).

set -e

REPO="${VIERNES_REPO:-https://github.com/CarlLince/viernes.git}"
APP_REPO="CarlLince/viernes-escucha"
DIR="$HOME/viernes"
ENVFILE="$HOME/.viernes_env"
SIN_APP=0
[ "${1:-}" = "--sin-app" ] && SIN_APP=1

echo "== Instalando Viernes =="

# 1) Paquetes base
export DEBIAN_FRONTEND=noninteractive
pkg update -y && pkg upgrade -y
pkg install -y python python-pip git curl termux-api clang make libffi openssl

# 2) Descargar (o actualizar) Viernes: viernes.py, cara.py, seguridad.py, pantalla.py, vad.py, notas.py...
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only || echo "AVISO: no pude actualizar Viernes (¿cambios locales?). Sigo con lo que ya tienes."
elif [ -d "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  # Ya había una carpeta con archivos sueltos (bajados a mano): se aparta, se baja Viernes y se regresa lo que no sea de Viernes.
  RESPALDO="$HOME/viernes_respaldo_$(date +%Y%m%d-%H%M%S)"
  mv "$DIR" "$RESPALDO"
  if ! git clone "$REPO" "$DIR"; then
    rm -rf "$DIR"
    mv "$RESPALDO" "$DIR"
    echo "No pude bajar Viernes (¿hay internet?). Dejé tu carpeta como estaba."
    exit 1
  fi
  for f in "$RESPALDO"/* "$RESPALDO"/.[!.]*; do
    [ -e "$f" ] || continue
    [ -e "$DIR/$(basename "$f")" ] || mv "$f" "$DIR"/
  done
  echo "Tu carpeta anterior quedó en $RESPALDO (lo que no era de Viernes, como modelos o notas, volvió a $DIR)."
else
  git clone "$REPO" "$DIR"
fi

# 3) Herramientas de audio que use el código (se detectan solas)
EXTRA=""
for t in mpv ffmpeg sox play-audio; do
  if grep -rqs --include='*.py' "$t" "$DIR"; then EXTRA="$EXTRA $t"; fi
done
if grep -rqs --include='*.py' "ffplay" "$DIR"; then EXTRA="$EXTRA ffmpeg"; fi
if [ -n "$EXTRA" ]; then pkg install -y $EXTRA; fi

# 4) Librerías de Python
cd "$DIR"
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# 5) Clave de Gemini (se pide una sola vez)
if [ ! -f "$ENVFILE" ]; then
  # AJUSTA: detecta el nombre de variable que usa el código (si no, GEMINI_API_KEY)
  VAR=$(grep -rhoE --include='*.py' "(environ\[|environ\.get\(|getenv\()[\"'][A-Za-z_]+[\"']" "$DIR" \
        | grep -oE "[A-Z][A-Z_]{3,}" | grep -E "KEY|API" | head -1 || true)
  VAR=${VAR:-GEMINI_API_KEY}

  echo
  echo "Crea tu clave gratis en https://aistudio.google.com/apikey y pégala aquí."
  read -r -s -p "Clave de Gemini: " KEY < /dev/tty
  echo
  if [ -z "$KEY" ]; then
    echo "No pegaste ninguna clave. Ejecuta el instalador otra vez."
    exit 1
  fi
  {
    echo "export $VAR='$KEY'"
    echo "export GEMINI_API_KEY='$KEY'"
    echo "export GOOGLE_API_KEY='$KEY'"
  } > "$ENVFILE"
  chmod 600 "$ENVFILE"
fi
if ! grep -qs "viernes_env" "$HOME/.bashrc"; then
  echo '[ -f "$HOME/.viernes_env" ] && . "$HOME/.viernes_env"' >> "$HOME/.bashrc"
fi

# 6) Comando "viernes" (carga la clave y lanza el agente)
cat > "$PREFIX/bin/viernes" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
[ -f "$HOME/.viernes_env" ] && . "$HOME/.viernes_env"
cd "$HOME/viernes" && exec python viernes.py "$@"
EOF
chmod +x "$PREFIX/bin/viernes"

# 7) Instrucciones de control de pantalla para el agente (se mezclan con tu notas.txt sin borrarlo)
python3 - "$DIR" <<'PYNOTAS_INST'
import os
import re
import sys

d = sys.argv[1]
plantilla = os.path.join(d, "notas_pantalla.txt")
destino = os.path.join(d, "notas.txt")
if not os.path.exists(plantilla):
    print("(no hay notas_pantalla.txt; me salto las instrucciones de pantalla)")
    sys.exit(0)
with open(plantilla, encoding="utf-8") as f:
    bloque = f.read().strip("\n") + "\n"
texto = ""
if os.path.exists(destino):
    with open(destino, encoding="utf-8") as f:
        texto = f.read()
patron = re.compile(r"=== CONTROL DE PANTALLA ===.*?=== FIN CONTROL DE PANTALLA ===\n?", re.S)
if patron.search(texto):
    texto = patron.sub(lambda m: bloque, texto)
else:
    texto = texto.rstrip("\n") + ("\n\n" if texto.strip() else "") + bloque
with open(destino, "w", encoding="utf-8") as f:
    f.write(texto)
print("Instrucciones de pantalla listas en notas.txt")
PYNOTAS_INST

# 8) Permite que Viernes Escucha lance a Viernes desde fuera de Termux
mkdir -p "$HOME/.termux" "$HOME/.viernes"
if ! grep -qs "^allow-external-apps *= *true" "$HOME/.termux/termux.properties"; then
  echo "allow-external-apps = true" >> "$HOME/.termux/termux.properties"
fi
termux-reload-settings 2>/dev/null || true

# 9) Comprueba que Termux:API responde
if ! timeout 10 termux-battery-status > /dev/null 2>&1; then
  echo
  echo "AVISO: Termux:API no responde. Instala la app Termux:API"
  echo "(de la misma fuente que Termux, F-Droid o GitHub) y ábrela una vez."
fi

# 10) Revisión rápida del código y de las reglas de seguridad
echo
echo "== Revisando Viernes =="
( cd "$DIR" && python -m py_compile viernes.py cara.py notas.py vad.py seguridad.py pantalla.py ) \
  && echo "Código sin errores de sintaxis" || echo "AVISO: algún archivo de Viernes tiene errores de sintaxis (mira el mensaje de arriba)."
( cd "$DIR" && python seguridad.py | tail -n 1 ) || echo "AVISO: la autoprueba de seguridad.py falló."

# 11) App Viernes Escucha (aplausos, palabra «viernes», cara flotante y control de pantalla)
if [ "$SIN_APP" -eq 0 ]; then
  echo
  echo "== App Viernes Escucha =="
  if pm list packages 2>/dev/null | grep -q "mx.viernes.escucha" && [ -z "${ACTUALIZAR_APP:-}" ]; then
    echo "Ya está instalada. Para bajar la versión más nueva: ACTUALIZAR_APP=1 bash instalar.sh"
  else
    APK_URL=$(curl -fsSL "https://api.github.com/repos/$APP_REPO/releases/latest" | python3 -c '
import json, sys
try:
    for a in json.load(sys.stdin).get("assets", []):
        if a.get("name", "").endswith(".apk"):
            print(a["browser_download_url"])
            break
except Exception:
    pass
' 2>/dev/null || true)
    if [ -n "$APK_URL" ]; then
      if [ ! -d "$HOME/storage/downloads" ]; then
        echo "Android va a pedir permiso para guardar archivos: acéptalo."
        termux-setup-storage || true
        sleep 6
      fi
      DESTINO="$HOME/storage/downloads"
      [ -d "$DESTINO" ] || DESTINO="$HOME"
      if curl -fL --progress-bar -o "$DESTINO/Viernes-Escucha.apk" "$APK_URL"; then
        echo "APK guardado en $DESTINO/Viernes-Escucha.apk"
        termux-open "$DESTINO/Viernes-Escucha.apk" 2>/dev/null || true
      else
        echo "No pude bajar el APK; abro la página de descargas."
        termux-open-url "https://github.com/$APP_REPO/releases/latest" 2>/dev/null || true
      fi
    else
      echo "No pude consultar la última versión; abro la página de descargas."
      termux-open-url "https://github.com/$APP_REPO/releases/latest" 2>/dev/null || true
    fi
  fi
fi

cat <<'FIN'

Listo. Para usar Viernes en la terminal escribe:  viernes

Falta, a mano (5 minutos):
 1) Ajustes > Apps > Termux:API > Permisos > Micrófono.
 2) Batería "sin restricciones" para Termux, Termux:API y Viernes Escucha.
 3) Instala Viernes Escucha (si no se abrió solo, ábrelo desde Descargas: Viernes-Escucha.apk).
    Ábrela y toca: Dar permisos, Descargar modelo de voz y Probar enlace con Termux.
    Dale también "Mostrar sobre otras apps" (la burbuja con el orbe).
 4) Control de pantalla (para que Viernes vea y toque tu celular):
    - En la app toca «1. Activar el servicio» y enciende «Viernes (pantalla)».
      Si Android no te deja: Información de la app > menú ⋮ > «Permitir ajustes restringidos».
    - Toca «2. Vincular pantalla con Termux» (marca la casilla sola).
    - Prueba en Termux:  python ~/viernes/pantalla.py leer
    Si actualizas la app y deja de responder, repite esos dos botones.
 5) Para despertarlo: toca «Iniciar en horario» (7 a 14 h) o «Probar 30 minutos», aplaude dos veces y di «viernes».
FIN
