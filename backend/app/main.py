from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
import os
from pathlib import Path

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers


app = FastAPI(title="语言神wiki")

register_error_handlers(app)

app.include_router(api_router, prefix="/api/v1")


@app.get("/api/v1/ops/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/ops/ready")
def ready() -> dict:
    database_url = os.getenv("DATABASE_URL", settings.database_url)
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database not ready") from exc


@app.get("/api/v1/ops/version")
def version() -> dict:
    return {"version": "0.1.0"}


# ---- 前端静态服务（生产单端口部署） ----
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # API 路由已在上面注册，这里只处理前端
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        target = _DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
