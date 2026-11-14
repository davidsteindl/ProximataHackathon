from typing import Literal

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.site_api import router
from app.cad_api import router as cad_router
from app.ingestion_api import router as ingestion_router
from app.flag_api import router as flag_router
from app.review_api import router as review_router

from app.outbox import router as outbox_router
from app.telegram_compliance import router as telegram_router
from app.context_api import router as context_router
from app.proposal_api import router as proposal_router

app = FastAPI(title="SiteMind API")
app.include_router(router)
app.include_router(cad_router)
app.include_router(ingestion_router)
app.include_router(flag_router)
app.include_router(review_router)
app.include_router(outbox_router)
app.include_router(telegram_router)
app.include_router(context_router)
app.include_router(proposal_router)


@app.middleware("http")
async def restrict_agent_writes(request: Request, call_next):
    client = request.headers.get("X-SiteMind-Client", "").lower()
    if client in {"mcp", "chat", "agent"} and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.method != "POST" or request.url.path != "/agent/proposals":
            return JSONResponse(status_code=403, content={"detail": "Agents may only create unapproved Proposals"})
    return await call_next(request)


class Health(BaseModel):
    api: Literal["ok"] = "ok"
    db: Literal["ok", "error"]


@app.get("/health", response_model=Health, responses={503: {"model": Health}})
def health(response: Response) -> Health:
    try:
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SELECT 1").fetchone()
    except psycopg.Error:
        response.status_code = 503
        return Health(db="error")
    return Health(db="ok")
