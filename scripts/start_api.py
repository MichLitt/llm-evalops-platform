"""Start the FastAPI server. Run with: uv run python scripts/start_api.py"""

import uvicorn

from llm_evalops_platform.app import create_app
from llm_evalops_platform.config import settings

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
