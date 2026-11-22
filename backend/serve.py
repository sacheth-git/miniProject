"""Production entrypoint: one process serves the built website and the API under /api.

Used by the Docker image (Hugging Face Spaces). Locally, from backend/:
    .\\.venv\\Scripts\\python.exe -m uvicorn serve:app --port 7860
after building the frontend (npm run build in frontend/).
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.responses import FileResponse, PlainTextResponse

from app.main import app as api

DIST = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[1] / "frontend" / "dist")).resolve()
INDEX = DIST / "index.html"


async def app(scope, receive, send):  # type: ignore[no-untyped-def]
    if scope["type"] == "lifespan":
        await api(scope, receive, send)  # runs the API's startup (model warm-up) and shutdown
        return
    path: str = scope.get("path", "/")
    if path == "/api" or path.startswith("/api/"):
        sub = path[4:] or "/"
        await api(dict(scope, path=sub, raw_path=sub.encode()), receive, send)
        return
    if scope["type"] != "http":
        return
    # Static files from the Vite build; any other path is a client-side route -> index.html.
    rel = path.lstrip("/")
    target = (DIST / rel).resolve() if rel else INDEX
    if rel and target.is_file() and DIST in target.parents:
        immutable = rel.startswith("assets/")
        headers = {"Cache-Control": "public, max-age=31536000, immutable" if immutable else "public, max-age=3600"}
        response = FileResponse(target, headers=headers)
    elif INDEX.is_file():
        response = FileResponse(INDEX, headers={"Cache-Control": "no-cache"})
    else:
        response = PlainTextResponse("Frontend not built. Run npm run build in frontend/.", status_code=503)
    await response(scope, receive, send)
