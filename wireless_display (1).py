
import asyncio
import io
import secrets
import socket
from concurrent.futures import ThreadPoolExecutor

import mss
import qrcode
from aiohttp import web
from PIL import Image

PORT = 8000
MAX_WIDTH = 1600  # wider screens are scaled down to this width for speed
QUALITY = 60      # JPEG quality: lower is faster but blurrier
FPS = 30
MONITOR = 2       

TOKEN = secrets.token_urlsafe(6)            
grabber = ThreadPoolExecutor(max_workers=1)  
_sct = None

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wireless display</title>
<style>
html, body { margin: 0; height: 100%; background: #000; }
canvas { width: 100vw; height: 100vh; object-fit: contain; }
#s { position: fixed; inset: 0; display: grid; place-items: center; margin: 0;
color: #9a9a9a; font: 16px system-ui, sans-serif; pointer-events: none; }
</style>
<canvas id="c"></canvas>
<p id="s">Connecting to your PC…</p>
<script>
const c = document.getElementById("c"), s = document.getElementById("s");
const ctx = c.getContext("2d");
function connect() {
    const ws = new WebSocket(`ws://${location.host}/ws${location.search}`);
    ws.onmessage = async (e) => {
    const bmp = await createImageBitmap(e.data);
    if (c.width !== bmp.width || c.height !== bmp.height) {
        c.width = bmp.width;
        c.height = bmp.height;
    }
    ctx.drawImage(bmp, 0, 0);
    s.style.display = "none";
    };
    ws.onclose = () => {
    s.textContent = "Connection lost. Reconnecting…";
    s.style.display = "grid";
    setTimeout(connect, 1000);
    };
}
connect();
c.onclick = () => document.documentElement.requestFullscreen?.();
</script>"""


def grab_jpeg() -> bytes:
    global _sct
    if _sct is None:
        _sct = mss.mss()
    monitors = _sct.monitors
    shot = _sct.grab(monitors[MONITOR] if MONITOR < len(monitors) else monitors[1])
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, img.height * MAX_WIDTH // img.width), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=QUALITY)
    return buf.getvalue()


def authorized(request) -> bool:
    return secrets.compare_digest(request.query.get("k", "").encode(), TOKEN.encode())


async def index(request):
    if not authorized(request):
        return web.Response(status=403, text="This link is missing its key. Scan the QR code shown on your PC.")
    return web.Response(text=PAGE, content_type="text/html")


async def stream(request):
    if not authorized(request):
        raise web.HTTPForbidden()
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    loop = asyncio.get_running_loop()
    try:
        while not ws.closed:
            start = loop.time()
            frame = await loop.run_in_executor(grabber, grab_jpeg)
            await ws.send_bytes(frame)
            await asyncio.sleep(max(0, 1 / FPS - (loop.time() - start)))
    except ConnectionResetError:
        pass
    return ws


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # no packets are sent; this just picks the Wi-Fi adapter
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    with mss.mss() as sct:
        print("Screens (set MONITOR at the top to the number you want to stream):")
        for i, m in enumerate(sct.monitors[1:], start=1):
            print(f"  {i}: {m['width']}x{m['height']} at ({m['left']}, {m['top']})")
        if MONITOR >= len(sct.monitors):
            print(f"  Screen {MONITOR} not found, streaming screen 1 instead.")
    url = f"http://{local_ip()}:{PORT}/?k={TOKEN}"
    print(f"\ntest3 (same Wi-Fi):\n{url}\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    try:
        qr.print_ascii(invert=True)
    except UnicodeEncodeError:
        pass  

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws", stream)])
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)