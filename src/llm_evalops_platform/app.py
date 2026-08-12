from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from llm_evalops_platform.api import compare, gate, ingest, review, runs
from llm_evalops_platform.storage.db import db


def create_app() -> FastAPI:
    app = FastAPI(
        title="LLM EvalOps Platform",
        version="0.1.0",
        description="Agent eval, observability, and release platform",
    )

    db.init_db()

    app.include_router(ingest.router, prefix="/v1")
    app.include_router(runs.router, prefix="/v1")
    app.include_router(compare.router, prefix="/v1")
    app.include_router(gate.router, prefix="/v1")
    app.include_router(review.router, prefix="/v1")
    app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "ui", html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
