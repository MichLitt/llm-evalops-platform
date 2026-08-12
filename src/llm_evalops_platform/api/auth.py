"""Optional Bearer authentication for the public EvalOps API.

An unset token deliberately keeps local development friction-free. Production
and Compose deployments set ``EVALOPS_API_TOKEN`` and require every `/v1`
request to present it; `/health` remains public for orchestration probes.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request, status


def require_api_token(request: Request) -> None:
    expected = os.environ.get("EVALOPS_API_TOKEN", "")
    if not expected:
        return
    provided = request.headers.get("Authorization", "")
    if not provided.startswith("Bearer ") or not hmac.compare_digest(provided[7:], expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")
