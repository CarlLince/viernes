"""Cara web de Viernes: un orbe animado que cambia según el estado.

En viernes.py:
    import cara
    cara.iniciar()                      # una vez, al arrancar
    cara.estado("escuchando")           # también: "pensando", "hablando", "reposo"
    cara.estado("hablando", respuesta)  # el segundo dato es el texto que se muestra

Probar sola:  python cara.py   (abre http://localhost:8765 y cambia de estado)
"""
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = 8765
ESTADOS = ("reposo", "escuchando", "pensando", "hablando")
_actual = {"estado": "reposo", "texto": ""}


def estado(nuevo, texto=""):
    """Cambia lo que muestra la cara. Nunca lanza errores."""
    if nuevo in ESTADOS:
        _actual["estado"] = nuevo
        _actual["texto"] = str(texto or "")[:300]


class _Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if self.path.startswith("/estado"):
            cuerpo = json.dumps(_actual).encode()
            tipo = "application/json"
        else:
            cuerpo = _HTML.encode("utf-8")
            tipo = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(cuerpo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class _Servidor(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


def iniciar(puerto=PUERTO, red=False, abrir=False):
    """Levanta la cara en segundo plano.

    red=True  -> también se puede ver desde otro celular en la misma Wi-Fi.
    abrir=True -> abre el navegador solo (necesita Termux:API).
    """
    try:
        servidor = _Servidor(("0.0.0.0" if red else "127.0.0.1", puerto), _Manejador)
    except OSError:
        return False
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    if abrir:
        try:
            subprocess.Popen(
                ["termux-open-url", "http://localhost:%d" % puerto],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    return True


_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#000000">
<title>Viernes</title>
<style>
html,body{margin:0;height:100%;background:#000;overflow:hidden;color:#d8f4ff;font-family:system-ui,sans-serif;user-select:none;-webkit-user-select:none}
canvas{position:fixed;left:0;top:0;width:100%;height:100%}
#nom{position:fixed;top:5%;width:100%;text-align:center;letter-spacing:.5em;font-size:14px;opacity:.5}
#pie{position:fixed;left:0;right:0;bottom:8%;text-align:center;padding:0 8%}
#est{font-size:20px;letter-spacing:.15em;text-transform:uppercase}
#txt{margin-top:10px;font-size:15px;opacity:.7;line-height:1.4;max-height:6.5em;overflow:hidden}
</style></head><body>
<canvas id="c"></canvas>
<div id="nom">VIERNES</div>
<div id="pie"><div id="est"></div><div id="txt"></div></div>
<script>
const c=document.getElementById('c'),x=c.getContext('2d');
const elE=document.getElementById('est'),elT=document.getElementById('txt');
let W=0,H=0,S=0;
function ajustar(){const d=window.devicePixelRatio||1;W=c.width=Math.round(innerWidth*d);H=c.height=Math.round(innerHeight*d);S=Math.min(W,H);}
addEventListener('resize',ajustar);ajustar();
const PAL={reposo:[200,.35,.15],escuchando:[150,.75,.45],pensando:[35,.85,1.6],hablando:[185,1,.7],offline:[220,.12,.05]};
const ETQ={reposo:'En espera',escuchando:'Escuchando…',pensando:'Pensando…',hablando:'Hablando…',offline:'Sin conexión'};
const peso={reposo:1,escuchando:0,pensando:0,hablando:0,offline:0};
const act=PAL.reposo.slice();
let est='reposo',amp=0,fase=0,tPrev=0,tono=200;
const mez=(a,b,k)=>a+(b-a)*k;
const col=a=>'hsla('+tono+',100%,60%,'+a+')';
elE.textContent=ETQ.reposo;
function anillo(cx,cy,r,n,hueco,ang,ancho,a){
  x.lineWidth=ancho*S*.008;x.strokeStyle=col(a);
  const paso=Math.PI*2/n;
  for(let i=0;i<n;i++){x.beginPath();x.arc(cx,cy,r,ang+i*paso,ang+i*paso+paso*(1-hueco));x.stroke();}
}
function dibujar(ms){
  const t=ms/1000,dt=Math.min(.05,t-tPrev);tPrev=t;
  const o=PAL[est];
  for(let i=0;i<3;i++)act[i]=mez(act[i],o[i],.06);
  for(const k in peso)peso[k]=mez(peso[k],k===est?1:0,.08);
  const objetivo=est==='hablando'?.3+.7*Math.abs(Math.sin(t*9)*Math.sin(t*5.3+1)):est==='escuchando'?.2+.1*Math.sin(t*3):.06+.05*Math.sin(t*1.3);
  amp=mez(amp,objetivo,.25);
  fase+=dt*act[2];
  tono=act[0];const v=act[1];
  x.clearRect(0,0,W,H);
  const cx=W/2,cy=H*.42,R=S*.2;
  const g=x.createRadialGradient(cx,cy,R*.1,cx,cy,R*(1.9+amp*.6));
  g.addColorStop(0,col(.5*v+.25*amp));g.addColorStop(.5,col(.12*v));g.addColorStop(1,col(0));
  x.fillStyle=g;x.fillRect(0,0,W,H);
  x.beginPath();x.arc(cx,cy,R*(.36+.12*amp),0,Math.PI*2);
  x.fillStyle='hsla('+tono+',100%,'+(65+25*amp)+'%,'+(.45+.45*v)+')';x.fill();
  anillo(cx,cy,R*.62,3,.35,fase,.9,.9*v+.1);
  anillo(cx,cy,R*.82,8,.45,-fase*1.3,.6,.7*v+.1);
  anillo(cx,cy,R*1.02,36,.5,fase*.7,.4,.5*v+.1);
  if(peso.escuchando>.01)for(let j=0;j<3;j++){const p=(t*.6+j/3)%1;x.lineWidth=S*.004;x.strokeStyle=col((1-p)*.6*peso.escuchando);x.beginPath();x.arc(cx,cy,R*(1.1+p*.9),0,Math.PI*2);x.stroke();}
  if(peso.pensando>.01)for(let j=0;j<3;j++){const a=t*3.2+j*2.094,r=R*1.28;x.beginPath();x.arc(cx+Math.cos(a)*r,cy+Math.sin(a)*r,S*.013,0,Math.PI*2);x.fillStyle=col(.9*peso.pensando);x.fill();}
  if(peso.hablando>.01){x.lineWidth=S*.007;x.lineCap='round';x.strokeStyle=col(.9*peso.hablando);const n=48;for(let i=0;i<n;i++){const a=i/n*Math.PI*2,l=R*.28*(.15+Math.abs(Math.sin(i*1.7+t*8)*Math.sin(i*.9-t*5.3)))*peso.hablando,r0=R*1.2;x.beginPath();x.moveTo(cx+Math.cos(a)*r0,cy+Math.sin(a)*r0);x.lineTo(cx+Math.cos(a)*(r0+l),cy+Math.sin(a)*(r0+l));x.stroke();}x.lineCap='butt';}
  requestAnimationFrame(dibujar);
}
requestAnimationFrame(dibujar);
async function sondear(){
  try{const r=await fetch('/estado',{cache:'no-store'});const j=await r.json();est=PAL[j.estado]?j.estado:'reposo';elE.textContent=ETQ[est];elT.textContent=j.texto||'';}
  catch(e){est='offline';elE.textContent=ETQ.offline;elT.textContent='';}
}
setInterval(sondear,300);sondear();
let wl=null;
addEventListener('click',async()=>{
  try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen();}catch(e){}
  try{if(navigator.wakeLock&&!wl)wl=await navigator.wakeLock.request('screen');}catch(e){}
});
</script></body></html>
"""


if __name__ == "__main__":
    if not iniciar(abrir=True):
        print("El puerto %d ya está en uso (¿Viernes ya está abierto?)." % PUERTO)
        sys.exit(1)
    print("Cara en http://localhost:%d  (Ctrl+C para salir)" % PUERTO)
    demo = [
        ("reposo", "En espera"),
        ("escuchando", "Te escucho…"),
        ("pensando", "Déjame pensar…"),
        ("hablando", "Hola, soy Viernes. Así me verás cuando hable."),
    ]
    try:
        while True:
            for e, t in demo:
                estado(e, t)
                time.sleep(3.5)
    except KeyboardInterrupt:
        pass
