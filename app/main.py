from __future__ import annotations

import argparse
import webbrowser

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api import api_router
from app.utils.tunnel_manager import create_tunnel_info_endpoint, tunnel_manager


def create_app() -> FastAPI:
    app = FastAPI(
        title="Medicar AI API",
        description="API para búsqueda en catálogos y análisis de archivos con OpenAI GPT-4o-mini",
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/tunnel/info")
    async def get_tunnel_info():
        """
        Obtiene información del túnel ngrok activo.
        Útil para saber la URL pública actual.
        """
        return create_tunnel_info_endpoint()

    return app


app = create_app()


def parse_arguments():
    """
    Parsea argumentos de línea de comandos.
    """

    parser = argparse.ArgumentParser(description="Medicar AI API Server")
    parser.add_argument("--tunnel", action="store_true", help="Iniciar túnel ngrok automáticamente")
    parser.add_argument("--no-browser", action="store_true", help="No abrir navegador automáticamente")
    parser.add_argument("--port", type=int, default=8000, help="Puerto del servidor (default: 8000)")
    return parser.parse_args()


def start_server_with_tunnel(port: int = 8000, open_browser: bool = True):
    """
    Inicia el servidor con túnel ngrok automático.
    """
    print("[INICIO] Iniciando Medicar AI API con tunel publico...")

    public_url = tunnel_manager.start_tunnel(open_dashboard=True)

    if public_url:
        print(f"\n[OK] API disponible publicamente en: {public_url}")
        print(f"[DOCS] Documentacion: {public_url}/docs")
        print(f"[HEALTH] Health check: {public_url}/health")
        print(f"[INFO] Info tunel: {public_url}/tunnel/info")

        if open_browser:
            webbrowser.open(f"{public_url}/docs")
    else:
        print("[ERROR] No se pudo crear el tunel. Iniciando solo localmente...")
        if open_browser:
            webbrowser.open("http://localhost:8000/docs")

    try:
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
    except KeyboardInterrupt:
        print("\n[STOP] Deteniendo servidor...")
    finally:
        tunnel_manager.stop_tunnel()
        print("[BYE] Hasta luego!")


def main():
    args = parse_arguments()

    if args.tunnel:
        start_server_with_tunnel(port=args.port, open_browser=not args.no_browser)
    else:
        if not args.no_browser:
            webbrowser.open(f"http://localhost:{args.port}/docs")

        uvicorn.run("app.main:app", host="0.0.0.0", port=args.port, reload=True)


if __name__ == "__main__":
    main()

