from fastapi import FastAPI

from llm_evalops_platform.api import compare, gate, ingest, runs
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
