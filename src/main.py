"""Entrypoint del server: avvia API e PWA su 127.0.0.1:8000 (dietro il reverse proxy Caddy)."""
import logging

import uvicorn

from src.api import app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # Uvicorn si fida degli header X-Forwarded-For solo da 127.0.0.1 (Caddy): l'IP del client
    # usato dai limiti anti abuso è quindi quello reale.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
