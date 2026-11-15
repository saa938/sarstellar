"""Backup host for the static site on Modal (the primary is Vercel at sarstellar.earth).

    cd web && npm run build && cd .. && modal deploy modal_app/web_host.py

Serves web/dist (hash-routed single-page app) with byte-range support for the demo film.
"""

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi", "starlette>=0.40")
    .add_local_dir(DIST, "/site", copy=True)
)
app = modal.App("sarstellar-site", image=image)


@app.function(cpu=1.0, memory=1024, scaledown_window=1200, min_containers=0)
@modal.concurrent(max_inputs=200)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.gzip import GZipMiddleware

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(GZipMiddleware, minimum_size=1024)
    api.mount("/", StaticFiles(directory="/site", html=True), name="site")
    return api
