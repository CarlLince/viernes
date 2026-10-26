#!/data/data/com.termux/files/usr/bin/bash
# Instalador de Viernes para Termux
# Uso:  bash instalar.sh
# Requisito: tener instaladas las apps Termux y Termux:API (misma fuente).

set -e

REPO="https://github.com/CarlLince/viernes.git"   # AJUSTA si cambia el repo
DIR="$HOME/viernes"
ENVFILE="$HOME/.viernes_env"

echo "== Instalando Viernes =="

# 1) Paquetes base
pkg update -y && pkg upgrade -y
pkg install -y python python-pip git termux-api clang make libffi openssl

# 2) Descargar (o actualizar) Viernes
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
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

# 7) Permite que Viernes Escucha lance a Viernes desde fuera de Termux
mkdir -p "$HOME/.termux"
if ! grep -qs "^allow-external-apps *= *true" "$HOME/.termux/termux.properties"; then
  echo "allow-external-apps = true" >> "$HOME/.termux/termux.properties"
fi
termux-reload-settings 2>/dev/null || true

# 8) Comprueba que Termux:API responde
if ! timeout 10 termux-battery-status > /dev/null 2>&1; then
  echo
  echo "AVISO: Termux:API no responde. Instala la app Termux:API"
  echo "(de la misma fuente que Termux, F-Droid o GitHub) y ábrela una vez."
fi

cat <<'FIN'

Listo. Para usarlo escribe:  viernes

Falta, a mano (1 minuto):
 1) Ajustes > Apps > Termux:API > Permisos > Micrófono.
 2) Batería "sin restricciones" para Termux, Termux:API y Viernes Escucha.
 3) Instala Viernes Escucha; dale micrófono y el permiso para
    ejecutar comandos en Termux.
FIN

# Abre la descarga de Viernes Escucha (sube el APK a Releases del repo)
termux-open-url "https://github.com/CarlLince/viernes-escucha/releases/latest" 2>/dev/null || true
