import asyncio
import http.server
import socketserver
import threading
from pathlib import Path
from playwright.async_api import async_playwright

import functools

PORT = 8899
BASE_DIR = Path(__file__).resolve().parent.parent

httpd_server = None

def run_server():
    global httpd_server
    socketserver.TCPServer.allow_reuse_address = True
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(BASE_DIR))
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd_server = httpd
        httpd.serve_forever()

async def generate_screenshot():
    # Iniciar servidor local en background
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1200, "height": 630},
            device_scale_factor=2
        )
        page = await context.new_page()
        
        url = f"http://localhost:{PORT}/templates/share.html"
        await page.goto(url, wait_until="networkidle")
        
        # Esperar a que la tarjeta esté hidratada
        await page.wait_for_selector("#cardTableBody tr", timeout=10000)
        
        # Ocultar la barra de herramientas de navegación durante la captura
        await page.evaluate("""
            const header = document.querySelector('header');
            if (header) header.style.display = 'none';
            document.body.style.padding = '0';
            document.body.style.margin = '0';
            document.body.style.backgroundColor = '#09090b';
        """)
        
        card = await page.query_selector("#shareCard")
        if card:
            output_path = BASE_DIR / "og-preview.png"
            await card.screenshot(path=str(output_path), type="png")
            print(f"[OK] Vista previa social generada en: {output_path} (2400x1260 px)")
        else:
            print("[ERROR] No se encontró el selector #shareCard")

        await browser.close()

    if httpd_server:
        httpd_server.shutdown()

if __name__ == "__main__":
    asyncio.run(generate_screenshot())
