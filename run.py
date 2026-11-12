"""Produktionsstart (Windows-Dienst via NSSM, oder im Docker-Container).

Konfiguration über Umgebungsvariablen:
  CYBERLAB_HOST   (Standard 0.0.0.0 im Container, 127.0.0.1 hinter lokalem Proxy)
  CYBERLAB_PORT   (Standard 8080)
  CYBERLAB_SCHEME (http|https – für korrekte URLs hinter TLS-Proxy)
  CYBERLAB_TRUST_PROXY=1  hinter Reverse-Proxy setzen (wertet X-Forwarded-* aus)
"""
import logging
import os

from waitress import serve

from cyberlab import create_app
from cyberlab.labs import start_reaper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    start_reaper(app)
    host = os.environ.get("CYBERLAB_HOST", "127.0.0.1")
    port = int(os.environ.get("CYBERLAB_PORT", "8080"))
    app.logger.info("Golm CyberLab läuft auf http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=16,
          url_scheme=os.environ.get("CYBERLAB_SCHEME", "http"), ident="CyberLab")
