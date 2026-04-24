"""Start the normalization worker. Run with: uv run python scripts/start_worker.py"""

import logging

from llm_evalops_platform.storage.db import db
from llm_evalops_platform.worker.normalizer import run_loop

logging.basicConfig(level=logging.INFO, format="%(message)s")

if __name__ == "__main__":
    db.init_db()
    run_loop()
