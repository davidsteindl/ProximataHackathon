"""Read-only replay preflight; credentials and provider endpoints are never returned."""

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Replay"])


class ReplayConfiguration(BaseModel):
    offline_ready: bool


@router.get("/replay/config", response_model=ReplayConfiguration)
def replay_configuration():
    # Both extraction and the advisor select the cache with this setting.
    return ReplayConfiguration(offline_ready=os.environ.get("LLM_PROVIDER", "cached") == "cached")
