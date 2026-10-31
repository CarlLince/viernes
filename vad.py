"""Detecta cuándo empiezas y cuándo dejas de hablar, y corta la grabación en ese momento.

    import vad
    r = vad.grabar_hasta_silencio("/ruta/audio.m4a", maximo=15)
    # {"voz": True,  "segundos": 3.4, "razon": "silencio", ...}  hablaste y dejaste de hablar
    # {"voz": False, "segundos": 5.0, "razon": "sin_voz", ...}   nadie habló
    # None                                                      no se pudo: usa la grabación de siempre

Antes, una sola vez por celular:   python vad.py formatos   (descubre cómo oír en vivo)
Para probar y afinar:              python vad.py            (habla y calla; muestra qué detectó)

Cómo funciona: termux-microphone-record graba a un archivo que va creciendo. Si el archivo es
AAC "ADTS" o AMR, ffmpeg lo decodifica en vivo; si es un contenedor 3GP/MP4 con AMR, se sacan
los cuadros AMR del mdat a medida que se escriben. Un detector de volumen decide cuándo
empezaste y cuándo callaste. Al terminar deja el audio en `ruta` (m4a), como la grabación normal.
"""
import math
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from array import array

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(DIR, "vad_formato.txt")

# ---- Ajustes (afínalos con `python vad.py`) ----
RATE = 16000
MUESTRAS = 320            # un cuadro = 20 ms
PASO = MUESTRAS / RATE
INICIO_VOZ = 0.15         # segundos de voz seguida para dar por empezada la orden
FIN_SILENCIO = 1.0        # segundos callado, después de hablar, para terminar (sube a 1.3 si te corta)
ESPERA_INICIO = 5.0       # segundos máximos esperando a que empieces a hablar
UMBRAL_MIN = 350          # volumen mínimo (0 a 32767) para contar como voz
FACTOR_RUIDO = 3.0        # la voz debe superar 3 veces el ruido de fondo
CALIBRACION = 20          # cuadros (0.4 s) para medir el ruido de fondo al empezar
RUIDO_MAX = 450           # tope del ruido de fondo medido (si hablas de inmediato, no lo confunde con voz)

# Formatos que se prueban, del mejor al peor: (codificador, extensión)
FORMATOS = [("aac", ".aac"), ("amr_wb", ".3gp"), ("amr_nb", ".3gp")]


class Detector:
    """Decide, cuadro por cuadro, cuándo empieza y cuándo termina la voz."""

    def __init__(self):
        self.t = 0.0
        self.ruido = None
        self.empezo = False
        self.fin = False
        self.t_inicio = None
        self.t_fin = None
        self.pico = 0.0
        self._calib = []
        self._voz_seguida = 0.0
        self._silencio = 0.0

    @property
    def umbral(self):
        return max(UMBRAL_MIN, (self.ruido or 0.0) * FACTOR_RUIDO)

    def procesar(self, rms):
        self.t += PASO
        self.pico = max(self.pico, rms)
        if self.ruido is None:
            # Primeros cuadros: se mide el ruido de fondo y luego se revisan con ese dato,
            # para no perder una orden muy corta dicha de inmediato.
            self._calib.append((self.t, rms))
            if len(self._calib) < CALIBRACION:
                return
            niveles = sorted(r for _, r in self._calib if r > 1.0) or [0.0]
            self.ruido = min(niveles[len(niveles) // 10], RUIDO_MAX)
            pendientes, self._calib = self._calib, []
            for t, r in pendientes:
                self._evaluar(t, r)
            return
        self._evaluar(self.t, rms)

    def _evaluar(self, t, rms):
        if self.fin:
            return
        if not self.empezo:
            if rms > self.umbral:
                self._voz_seguida += PASO
                if self._voz_seguida >= INICIO_VOZ:
                    self.empezo = True
                    self.t_inicio = t - self._voz_seguida
                    self._silencio = 0.0
            else:
                self._voz_seguida = 0.0
                self.ruido = self.ruido * 0.97 + rms * 0.03   # el ruido de fondo se adapta
        elif rms > self.umbral * 0.6:
            self._silencio = 0.0
        else:
            self._silencio += PASO
            if self._silencio >= FIN_SILENCIO:
                self.fin = True
                self.t_fin = t


def _rms(muestras):
    if not muestras:
        return 0.0
    return math.sqrt(sum(x * x for x in muestras) / len(muestras))


def _limpiar(*rutas):
    for r in rutas:
        try:
            os.remove(r)
        except OSError:
            pass


def _parar_grabacion():
    try:
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _parar_en_segundo_plano():
    threading.Thread(target=_parar_grabacion, daemon=True).start()


def _tipo_de_archivo(ruta):
    """'adts' y 'amr' (sin contenedor) se oyen en vivo directo; 'contenedor' es mp4/3gp."""
    try:
        with open(ruta, "rb") as f:
            cab = f.read(16)
    except OSError:
        return "vacío"
    if len(cab) < 8:
        return "vacío"
    if cab[0] == 0xFF and (cab[1] & 0xF0) == 0xF0:
        return "adts"
    if cab[4:8] == b"ftyp":
        return "contenedor"
    if cab.startswith(b"#!AMR"):
        return "amr"
    return "otro"


def _inicio_mdat(ruta):
    """Posición donde empiezan los datos del mdat (None si todavía no se ve)."""
    try:
        with open(ruta, "rb") as f:
            pos = 0
            for _ in range(10):
                f.seek(pos)
                cab = f.read(16)
                if len(cab) < 8:
                    return None
                tam = int.from_bytes(cab[:4], "big")
                largo = 8
                if tam == 1 and len(cab) >= 16:
                    tam = int.from_bytes(cab[8:16], "big")
                    largo = 16
                if cab[4:8] == b"mdat":
                    return pos + largo
                if tam < 8:
                    return None
                pos += tam
    except OSError:
        return None
    return None


def _alimentar(vivo, enc, stdin, parar):
    """Hilo: pasa a ffmpeg los cuadros AMR que Android va escribiendo dentro del mdat."""
    magia = b"#!AMR-WB\n" if enc == "amr_wb" else b"#!AMR\n"
    try:
        inicio = None
        while inicio is None and not parar.is_set():
            inicio = _inicio_mdat(vivo)
            if inicio is None:
                time.sleep(0.03)
        if parar.is_set():
            return
        stdin.write(magia)
        stdin.flush()
        pos = inicio
        with open(vivo, "rb") as f:
            while not parar.is_set():
                f.seek(pos)
                datos = f.read(4096)
                if datos:
                    stdin.write(datos)
                    stdin.flush()
                    pos += len(datos)
                else:
                    time.sleep(0.02)
    except (OSError, ValueError):
        pass   # ffmpeg ya se cerró
    finally:
        try:
            stdin.close()
        except (OSError, ValueError):
            pass


def _abrir_fuente(vivo, enc, tipo):
    """Arranca ffmpeg para decodificar en vivo. Devuelve (proceso, evento_de_parada) o None."""
    salida = ["-f", "s16le", "-ar", str(RATE), "-ac", "1", "-flush_packets", "1", "pipe:1"]
    parar = threading.Event()
    if tipo in ("adts", "amr"):
        cmd = ["ffmpeg", "-loglevel", "quiet", "-fflags", "nobuffer", "-probesize", "4096",
               "-analyzeduration", "100000", "-follow", "1", "-i", "file:" + vivo] + salida
        entrada = subprocess.DEVNULL
    elif tipo == "contenedor" and enc in ("amr_wb", "amr_nb"):
        cmd = ["ffmpeg", "-loglevel", "quiet", "-fflags", "nobuffer", "-probesize", "64",
               "-analyzeduration", "0", "-f", "amr", "-i", "pipe:0"] + salida
        entrada = subprocess.PIPE
    else:
        return None
    try:
        proc = subprocess.Popen(cmd, stdin=entrada, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    if entrada == subprocess.PIPE:
        threading.Thread(target=_alimentar, args=(vivo, enc, proc.stdin, parar), daemon=True).start()
    return proc, parar


def _cerrar_fuente(proc, parar):
    parar.set()
    proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.SubprocessError:
        pass


def _formato_elegido():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            enc, ext = f.read().split()
            return enc, ext
    except (OSError, ValueError):
        return None


def _guardar_m4a(pcm, destino):
    """Guarda el audio ya decodificado (PCM 16 kHz mono) como m4a en `destino`."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
             "-i", "pipe:0", "-c:a", "aac", "-b:a", "48k", destino],
            input=pcm,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and os.path.exists(destino) and os.path.getsize(destino) > 0


def _iniciar_grabacion(vivo, enc, maximo):
    """Arranca el grabador y espera a que aparezca el archivo. Devuelve su tipo o None."""
    for _ in range(2):
        try:
            p = subprocess.Popen(
                ["termux-microphone-record", "-f", vivo, "-e", enc, "-l", str(int(maximo) + 3)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            threading.Thread(target=p.wait, daemon=True).start()
        except OSError:
            return None
        t0 = time.time()
        tipo = "vacío"
        while time.time() - t0 < 2.5 and tipo == "vacío":
            tipo = _tipo_de_archivo(vivo)
            time.sleep(0.03)
        if tipo != "vacío":
            return tipo
        _parar_grabacion()      # quizá había una grabación anterior sin cerrar
        time.sleep(0.3)
    return None


def grabar_hasta_silencio(ruta, maximo=15.0):
    """Graba hasta que dejes de hablar. Ver el principio del archivo para los resultados."""
    t_ini = time.time()
    formato = _formato_elegido()
    if not formato or not shutil.which("ffmpeg") or not shutil.which("termux-microphone-record"):
        return None
    enc, ext = formato
    vivo = os.path.splitext(ruta)[0] + "_vivo" + ext
    _limpiar(ruta, vivo)
    tipo = _iniciar_grabacion(vivo, enc, maximo)
    fuente = _abrir_fuente(vivo, enc, tipo) if tipo else None
    if fuente is None:
        _parar_en_segundo_plano()
        _limpiar(vivo)
        return None
    proc, parar = fuente

    det = Detector()
    buf = b""
    todo = bytearray()
    fd = proc.stdout.fileno()
    t_grab = time.time()
    ultimo_dato = t_grab
    t_primer = None
    razon = None
    t_fin_det = t_grab
    try:
        while razon is None:
            if time.time() - t_grab >= maximo:
                razon = "maximo"
            elif not det.empezo and det.t >= ESPERA_INICIO:
                razon = "sin_voz"
            elif select.select([fd], [], [], 0.1)[0]:
                datos = os.read(fd, 4096)
                if not datos:
                    razon = "error"
                    break
                if t_primer is None:
                    t_primer = time.time() - t_ini
                ultimo_dato = time.time()
                buf += datos
                todo += datos
                while len(buf) >= MUESTRAS * 2 and not det.fin:
                    cuadro, buf = buf[: MUESTRAS * 2], buf[MUESTRAS * 2:]
                    m = array("h")
                    m.frombytes(cuadro)
                    if sys.byteorder == "big":
                        m.byteswap()
                    det.procesar(_rms(m))
                if det.fin:
                    razon = "silencio"
            elif time.time() - ultimo_dato > 2.5:
                razon = "error"
    finally:
        t_fin_det = time.time()
        _cerrar_fuente(proc, parar)
        _parar_en_segundo_plano()      # no se espera a que Android cierre el grabador

    info = {
        "segundos": round(det.t, 1),
        "razon": razon,
        "ruido": int(det.ruido or 0),
        "umbral": int(det.umbral),
        "pico": int(det.pico),
        "arranque": round(t_primer or 0.0, 1),
    }
    _limpiar(vivo)
    if razon == "error":
        return None
    if not det.empezo:
        info.update(voz=False, razon="sin_voz")
        return info
    # Se guarda lo que ya se decodificó en vivo (sin esperar a que Android cierre su archivo),
    # recortando el silencio de los extremos.
    ini = max(0.0, (det.t_inicio or 0.0) - 0.4)
    fin = (det.t_fin - FIN_SILENCIO + 0.5) if det.t_fin else det.t
    fin = max(fin, ini + 0.5)
    pcm = bytes(todo[int(ini * RATE) * 2: int(fin * RATE) * 2])
    if not _guardar_m4a(pcm, ruta):
        return None
    info["voz"] = True
    info["habla_de"] = round(det.t_inicio or 0.0, 1)
    info["habla_hasta"] = round(det.t_fin - FIN_SILENCIO, 1) if det.t_fin else round(det.t, 1)
    info["cierre"] = round(time.time() - t_fin_det, 1)
    return info


def _decodificar(ruta):
    """Decodifica un archivo terminado a PCM 16 kHz mono (para comparar). None si falla."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-loglevel", "quiet", "-i", ruta, "-f", "s16le", "-ar", str(RATE), "-ac", "1", "pipe:1"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def _coincide(en_vivo, terminado):
    """¿El audio decodificado en vivo es el mismo que el del archivo ya terminado?"""
    a = array("h")
    a.frombytes(en_vivo[: len(en_vivo) // 2 * 2])
    b = array("h")
    b.frombytes(terminado[: len(terminado) // 2 * 2])
    if len(a) < 8000 or len(b) < 8000:
        return False
    if a[:8000] == b[:8000]:
        return True
    patron = a[2000:4000]           # por si el archivo terminado trae un pequeño desfase
    for lag in range(-4800, 4801):
        ini = 2000 + lag
        if 0 <= ini and ini + 2000 <= len(b) and b[ini:ini + 2000] == patron:
            return True
    return False


def _prueba_en_vivo(enc, ext, segundos=2.5):
    ruta = os.path.join(DIR, "vad_prueba" + ext)
    _limpiar(ruta)
    _parar_grabacion()
    try:
        subprocess.run(["termux-microphone-record", "-f", ruta, "-e", enc, "-l", str(int(segundos) + 2)],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "no se pudo iniciar la grabación (¿está instalado termux-api?)", False
    t0 = time.time()
    tipo = "vacío"
    while time.time() - t0 < 2.5 and tipo == "vacío":
        tipo = _tipo_de_archivo(ruta)
        time.sleep(0.05)
    fuente = _abrir_fuente(ruta, enc, tipo)
    if fuente is None:
        _parar_grabacion()
        _limpiar(ruta)
        return "archivo tipo '%s': no se puede oír en vivo" % tipo, False
    proc, parar = fuente
    fd = proc.stdout.fileno()
    en_vivo = b""
    inicio = time.time()
    while time.time() - inicio < segundos:
        if select.select([fd], [], [], 0.1)[0]:
            datos = os.read(fd, 65536)
            if not datos:
                break
            en_vivo += datos
    _cerrar_fuente(proc, parar)
    _parar_grabacion()
    audio = len(en_vivo) / 2 / RATE
    if audio < 0.5 * segundos:
        _limpiar(ruta)
        return "tipo '%s': solo %.1f s de audio en vivo" % (tipo, audio), False
    if tipo != "contenedor":
        _limpiar(ruta)
        return "tipo '%s': %.1f s de audio en vivo" % (tipo, audio), True
    # En un contenedor 3GP/MP4 se comprueba que los cuadros sacados del mdat sean los correctos,
    # comparando con la decodificación normal del archivo ya terminado.
    terminado = None
    for _ in range(5):
        time.sleep(0.5)   # Android tarda un poco en cerrar el archivo
        terminado = _decodificar(ruta)
        if terminado:
            break
    _limpiar(ruta)
    if terminado is None or not _coincide(en_vivo, terminado):
        return "tipo '%s': %.1f s de audio, pero NO coincide con la grabación terminada" % (tipo, audio), False
    return "tipo '%s': %.1f s de audio en vivo, igual a la grabación terminada" % (tipo, audio), True


def diagnostico():
    """Prueba cada formato y guarda el primero que se puede oír en vivo."""
    print("Probando formatos de audio (unos 6 s cada uno). Habla durante la prueba.")
    elegido = None
    for enc, ext in FORMATOS:
        print("  %-7s " % enc, end="", flush=True)
        mensaje, sirve = _prueba_en_vivo(enc, ext)
        print("%s -> %s" % (mensaje, "SIRVE" if sirve else "no sirve"))
        if sirve:
            elegido = (enc, ext)
            break
    _parar_grabacion()
    if elegido:
        with open(CONFIG, "w", encoding="utf-8") as f:
            f.write("%s %s\n" % elegido)
        print("\nFormato elegido: %s (%s). Ya puedes probar:  python vad.py" % elegido)
        return True
    _limpiar(CONFIG)
    print("\nNingún formato se pudo oír en vivo en este celular. Pásame esta salida.")
    return False


def prueba():
    if not _formato_elegido():
        print("Primero corre:  python vad.py formatos")
        return
    ruta = os.path.join(DIR, "vad_prueba.m4a")
    print("Habla y luego calla; termina solo (máximo 10 s)...")
    t = time.time()
    r = grabar_hasta_silencio(ruta, maximo=10)
    print("Resultado:", r)
    print("Tardó %.1f s en total." % (time.time() - t))
    if r is None:
        print("No pudo oír en vivo; Viernes usaría la grabación de siempre.")
        return
    print("Ruido de fondo=%d, umbral=%d, pico de tu voz=%d" % (r["ruido"], r["umbral"], r["pico"]))
    if r["voz"]:
        print("Desglose: el grabador tardó %.1f s en dar audio | hablaste de %.1f s a %.1f s | "
              "cerrar y guardar tardó %.1f s" % (r["arranque"], r["habla_de"], r["habla_hasta"], r["cierre"]))
    if r["voz"]:
        print("Audio guardado en", ruta, "(se borra al volver a probar).")


if __name__ == "__main__":
    if sys.argv[1:2] == ["formatos"]:
        sys.exit(0 if diagnostico() else 1)
    prueba()
